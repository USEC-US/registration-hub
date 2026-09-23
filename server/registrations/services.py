import re

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Sequence

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Institution
from accounts.services.institutions import (
    normalize_institution_label,
    resolve_institution,
)
from tournaments.models import TournamentGame

from .payments import create_payment_intent
from .payment_settings import require_payment_settings
from .reservations import (
    active_registrations,
    expire_due_registrations,
    is_expired,
    lock_registration,
    payment_state,
)
from tournaments.payment_content import render_transfer_content
from .images import prepare_payment_image
from .models import (
    PaymentAttempt,
    PaymentIntent,
    Registration,
    RegistrationMember,
    RegistrationStatusEvent,
    RegistrationAccess,
)


@dataclass(frozen=True)
class RegistrationMemberInput:
    gamer_tag_snapshot: str
    is_captain: bool
    display_order: int
    first_name_snapshot: str = ""
    last_name_snapshot: str = ""
    date_of_birth_snapshot: date | None = None
    student_id_snapshot: str = ""
    roster_role: str = RegistrationMember.RosterRole.MAIN
    institution_id: int | None = None
    institution_label: str | None = None
    # Historical service callers only; never accepted by the API.
    school_snapshot: str = ""


def submit_registration(
    *,
    submitted_by,
    tournament_game_id: int,
    team_name: str,
    team_tag: str = "",
    members: Sequence[RegistrationMemberInput],
    submitter_role: str,
    contact_facebook_snapshot: str,
    contact_phone_snapshot: str,
    manager_name_snapshot: str = "",
    contact_email_snapshot: str = "",
    contact_discord_snapshot: str = "",
    proof_file=None,
    reference: str = "",
    payment_intent_token=None,
    access_credential: str | None = None,
    request_digest: str | None = None,
) -> Registration:
    from .access import hash_credential, lock_submission_credential, replay_registration

    credential_hash = (
        hash_credential(access_credential) if access_credential is not None else None
    )
    if credential_hash and (
        not isinstance(request_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", request_digest)
    ):
        raise ValidationError(
            "A canonical request digest is required for saved access."
        )
    attempt = None
    try:
        with transaction.atomic():
            if credential_hash:
                lock_submission_credential(credential_hash)
                replay = replay_registration(
                    credential_hash=credential_hash,
                    request_digest=request_digest,
                    submitted_by=submitted_by,
                    tournament_game_id=tournament_game_id,
                )
                if replay is not None:
                    return replay
            contacts = dict(
                manager_name_snapshot=manager_name_snapshot.strip(),
                contact_facebook_snapshot=contact_facebook_snapshot.strip(),
                contact_phone_snapshot=contact_phone_snapshot.strip(),
                contact_email_snapshot=contact_email_snapshot.strip(),
                contact_discord_snapshot=contact_discord_snapshot.strip(),
            )
            if submitter_role not in Registration.SubmitterRole.values:
                raise ValidationError({"submitter_role": "Choose captain or manager."})
            for field in ("contact_facebook_snapshot", "contact_phone_snapshot"):
                if not contacts[field]:
                    raise ValidationError({field: "This field is required."})
            if submitter_role == "manager" and not contacts["manager_name_snapshot"]:
                raise ValidationError(
                    {"manager_name_snapshot": "Enter the manager name."}
                )
            if submitter_role == "captain" and contacts["manager_name_snapshot"]:
                raise ValidationError(
                    {"manager_name_snapshot": "Captain submissions have no manager."}
                )
            if contacts["contact_email_snapshot"]:
                validate_email(contacts["contact_email_snapshot"])
            tournament_game = (
                TournamentGame.objects.select_for_update()
                .select_related("tournament")
                .get(pk=tournament_game_id)
            )
            if not tournament_game.tournament.is_published:
                raise ValidationError("Tournament is not published.")
            if (
                not tournament_game.registration_opens_at
                <= timezone.now()
                < tournament_game.registration_closes_at
            ):
                raise ValidationError("Registration is not open.")
            expire_due_registrations(division_id=tournament_game.pk)
            active = active_registrations(now=timezone.now()).filter(
                tournament_game=tournament_game
            )
            if (
                tournament_game.registration_capacity is not None
                and active.count() >= tournament_game.registration_capacity
            ):
                raise ValidationError("Registration capacity has been reached.")
            _validate_roster(
                tournament_game=tournament_game, team_name=team_name, members=members
            )
            normalized_team_tag = team_tag.strip()
            if tournament_game.is_team:
                if not re.fullmatch(r"[A-Za-z0-9]{2,5}", normalized_team_tag):
                    raise ValidationError(
                        {"team_tag": "Enter 2–5 letters (A–Z) or digits (0–9)."}
                    )
            elif normalized_team_tag:
                raise ValidationError(
                    {"team_tag": "Solo registrations have no team tag."}
                )
            if submitter_role == "captain" and not any(
                m.display_order == 1 and m.is_captain for m in members
            ):
                raise ValidationError(
                    {"members": "Captain submitters must occupy roster slot 1."}
                )
            if tournament_game.fee_amount <= 0 and (
                proof_file is not None or reference.strip()
            ):
                raise ValidationError(
                    {"proof_file": "This registration has no payment due."}
                )
            payment_settings = (
                require_payment_settings(
                    amount=tournament_game.fee_amount,
                    currency=tournament_game.fee_currency,
                )
                if tournament_game.fee_amount > 0
                else None
            )
            payment_intent = None
            if payment_intent_token:
                payment_intent = (
                    PaymentIntent.objects.select_for_update()
                    .filter(
                        token=payment_intent_token,
                        tournament_game=tournament_game,
                        registration__isnull=True,
                    )
                    .first()
                )
                if not payment_intent:
                    raise ValidationError(
                        {
                            "payment_intent_token": "Invalid or already used payment session."
                        }
                    )
                if (
                    payment_intent.amount != tournament_game.fee_amount
                    or payment_intent.currency != tournament_game.fee_currency
                ):
                    raise ValidationError(
                        {
                            "payment_intent_token": "The fee has changed. Contact the organizers before making any further payment."
                        }
                    )
            elif (
                submitted_by is None
                and proof_file is not None
                and tournament_game.fee_amount > 0
            ):
                raise ValidationError(
                    {
                        "payment_intent_token": "Load the transfer instructions before transferring and submitting proof."
                    }
                )
            prepared = (
                prepare_payment_image(proof_file) if proof_file is not None else None
            )
            resolved = []
            for member in members:
                school_label = member.institution_label or member.school_snapshot
                institution = None
                if member.institution_id or school_label.strip():
                    try:
                        institution = resolve_institution(
                            institution_id=member.institution_id,
                            institution_label=school_label,
                        )
                    except Institution.DoesNotExist as error:
                        raise ValidationError(
                            {"members": "Select an available institution."}
                        ) from error
                resolved.append((member, institution))
            claims = [
                (
                    normalize_institution_label(m.gamer_tag_snapshot),
                    m.institution_id,
                    normalize_institution_label(m.school_snapshot),
                )
                for m in RegistrationMember.objects.filter(registration__in=active)
            ]
            for member, institution in resolved:
                tag = normalize_institution_label(member.gamer_tag_snapshot)
                label = (
                    normalize_institution_label(institution.label)
                    if institution
                    else ""
                )
                if any(
                    tag == old_tag
                    and (
                        institution is None
                        or (old_id is None and not old_label)
                        or (
                            institution.pk == old_id
                            if old_id is not None
                            else label == old_label
                        )
                    )
                    for old_tag, old_id, old_label in claims
                ):
                    raise ValidationError(
                        {
                            "members": "A player already has an active registration in this division."
                        }
                    )
                claims.append((tag, institution.pk if institution else None, label))
            submitted_at = timezone.now()
            if submitted_at >= tournament_game.registration_closes_at:
                raise ValidationError("Registration is not open.")
            registration = Registration.objects.create(
                tournament_game=tournament_game,
                submitted_by=submitted_by,
                submitter_role=submitter_role,
                **contacts,
                team_name=team_name.strip(),
                team_tag=normalized_team_tag.upper(),
                status=Registration.Status.SUBMITTED,
                fee_amount_snapshot=tournament_game.fee_amount,
                fee_currency_snapshot=tournament_game.fee_currency,
                payment_hold_minutes_snapshot=payment_settings.payment_hold_minutes
                if payment_settings
                else None,
                payment_due_at=min(
                    submitted_at
                    + timedelta(minutes=payment_settings.payment_hold_minutes),
                    tournament_game.registration_closes_at,
                )
                if payment_settings
                else None,
            )
            RegistrationMember.objects.bulk_create(
                [
                    RegistrationMember(
                        registration=registration,
                        institution=institution,
                        user=submitted_by
                        if submitter_role == "captain" and member.display_order == 1
                        else None,
                        gamer_tag_snapshot=member.gamer_tag_snapshot.strip(),
                        first_name_snapshot=member.first_name_snapshot.strip(),
                        last_name_snapshot=member.last_name_snapshot.strip(),
                        date_of_birth_snapshot=member.date_of_birth_snapshot,
                        student_id_snapshot=member.student_id_snapshot.strip(),
                        school_snapshot=institution.label if institution else "",
                        is_captain=member.is_captain,
                        roster_role=member.roster_role,
                        display_order=display_order,
                    )
                    for display_order, (member, institution) in enumerate(
                        sorted(
                            resolved,
                            key=lambda pair: (
                                not pair[0].is_captain,
                                pair[0].display_order,
                            ),
                        ),
                        start=1,
                    )
                ]
            )
            if payment_intent:
                participant = (
                    registration.team_tag
                    or registration.members.order_by("display_order")
                    .first()
                    .gamer_tag_snapshot
                )
                payment_intent.transfer_content = render_transfer_content(
                    payment_intent.transfer_content_template,
                    participant,
                    payment_intent.transfer_content_limit,
                )
                payment_intent.registration = registration
                payment_intent.save(update_fields=["registration", "transfer_content"])
            elif tournament_game.fee_amount > 0:
                create_payment_intent(
                    tournament_game=tournament_game,
                    registration=registration,
                    payment_settings=payment_settings,
                )
            RegistrationStatusEvent.objects.create(
                registration=registration,
                from_status="",
                to_status=Registration.Status.SUBMITTED,
                actor=submitted_by,
            )
            if credential_hash:
                # Keep a savepoint around the durable unique constraint. No file has
                # been persisted yet, and the surrounding transaction owns all rows.
                with transaction.atomic():
                    RegistrationAccess.objects.create(
                        registration=registration,
                        credential_hash=credential_hash,
                        request_digest=request_digest,
                    )
            if prepared is not None:
                if is_expired(registration, now=timezone.now()):
                    raise ValidationError("Payment reservation has expired.")
                attempt = PaymentAttempt(
                    registration=registration,
                    method=PaymentAttempt.Method.MANUAL_PROOF,
                    status=PaymentAttempt.Status.PENDING,
                    amount=tournament_game.fee_amount,
                    currency=tournament_game.fee_currency,
                    proof_file=prepared,
                    reference=reference.strip(),
                )
                attempt.save()
            return registration
    except IntegrityError:
        if attempt is not None and attempt.proof_file and attempt.proof_file._committed:
            attempt.proof_file.delete(save=False)
        # Recover only a collision with a committed credential after the losing
        # transaction has rolled back all its rows. Other integrity errors remain
        # visible. Normal callers are already serialized by the key mutex.
        if credential_hash:
            replay = replay_registration(
                credential_hash=credential_hash,
                request_digest=request_digest,
                submitted_by=submitted_by,
                tournament_game_id=tournament_game_id,
            )
            if replay is not None:
                return replay
        raise
    except Exception:
        if attempt is not None and attempt.proof_file and attempt.proof_file._committed:
            attempt.proof_file.delete(save=False)
        raise


def _validate_roster(
    *,
    tournament_game: TournamentGame,
    team_name: str,
    members: Sequence[RegistrationMemberInput],
) -> None:
    for index, member in enumerate(members, 1):
        if (
            not member.first_name_snapshot.strip()
            or not member.last_name_snapshot.strip()
        ):
            raise ValidationError(
                {"members": f"Player {index}: first and last name are required."}
            )
        if (
            len(member.first_name_snapshot.strip()) > 150
            or len(member.last_name_snapshot.strip()) > 150
        ):
            raise ValidationError(
                {"members": f"Player {index}: names must not exceed 150 characters."}
            )
        if (
            type(member.date_of_birth_snapshot) is not date
            or member.date_of_birth_snapshot > timezone.localdate()
        ):
            raise ValidationError(
                {
                    "members": f"Player {index}: enter a valid date of birth that is not in the future."
                }
            )
        if len(member.student_id_snapshot.strip()) > 128:
            raise ValidationError(
                {
                    "members": f"Player {index}: student ID must not exceed 128 characters."
                }
            )
        if (
            tournament_game.tournament.students_only
            and not member.student_id_snapshot.strip()
        ):
            raise ValidationError(
                {
                    "members": f"Player {index}: student ID is required for student-only tournaments."
                }
            )
        if tournament_game.tournament.students_only and not (
            member.institution_id
            or (member.institution_label and member.institution_label.strip())
            or member.school_snapshot.strip()
        ):
            raise ValidationError(
                {
                    "members": f"Player {index}: school is required for student-only tournaments."
                }
            )
    if any(
        member.roster_role not in RegistrationMember.RosterRole.values
        for member in members
    ):
        raise ValidationError(
            {"members": "Choose a valid roster role for every player."}
        )
    if (
        sum(member.roster_role == "main" for member in members)
        != tournament_game.main_roster_size
    ):
        raise ValidationError(
            {
                "members": f"Exactly {tournament_game.main_roster_size} main players are required."
            }
        )
    if (
        sum(member.roster_role == "substitute" for member in members)
        > tournament_game.substitute_limit
    ):
        raise ValidationError(
            {
                "members": f"At most {tournament_game.substitute_limit} substitutes are allowed."
            }
        )
    if sum(member.is_captain for member in members) != 1:
        raise ValidationError("A registration must have exactly one captain.")
    if bool(team_name.strip()) != tournament_game.is_team:
        raise ValidationError("A team name is required exactly for team games.")
    if any(member.display_order < 1 for member in members):
        raise ValidationError("Roster display order must start at one.")
    if len({member.display_order for member in members}) != len(members):
        raise ValidationError("Roster display order must be unique.")
    if {member.display_order for member in members} != set(range(1, len(members) + 1)):
        raise ValidationError("Roster display order must be contiguous from one.")
    if any(not member.gamer_tag_snapshot.strip() for member in members):
        raise ValidationError("Every player needs a gamer tag.")


def _require_organizer(actor, permission: str) -> None:
    if actor.is_authenticated and actor.is_superuser:
        return
    if (
        actor.is_authenticated
        and actor.is_staff
        and actor.groups.filter(name="Organizers").exists()
        and actor.has_perm(permission)
    ):
        return
    raise PermissionDenied("An Organizer staff account is required.")


def _transition_registration(
    *,
    actor,
    registration_id: int,
    expected_status: str,
    to_status: str,
    note: str = "",
) -> Registration:
    _require_organizer(actor, "registrations.change_registration")
    with transaction.atomic():
        registration = lock_registration(registration_id)
        expire_due_registrations(division_id=registration.tournament_game_id)
        registration.refresh_from_db()
        if is_expired(registration, now=timezone.now()):
            raise ValidationError("Payment reservation has expired.")
        if registration.status != expected_status:
            raise ValidationError(
                f"Cannot move a {registration.status} registration to {to_status}."
            )
        if (
            to_status == Registration.Status.APPROVED
            and registration.fee_amount_snapshot > 0
            and payment_state(registration) != "VERIFIED"
        ):
            attempt = (
                registration.payment_attempts.filter(
                    status=PaymentAttempt.Status.PENDING
                )
                .order_by("-pk")
                .first()
            )
            if attempt is None or not attempt.proof_file:
                raise ValidationError("Payment proof is required before approval.")
            review_payment_attempt(
                actor=actor,
                payment_attempt_id=attempt.pk,
                status=PaymentAttempt.Status.VERIFIED,
            )
        registration.status = to_status
        registration.save(update_fields=("status", "updated_at"))
        RegistrationStatusEvent.objects.create(
            registration=registration,
            from_status=expected_status,
            to_status=to_status,
            actor=actor,
            note=note.strip(),
        )
        return registration


def start_review(*, actor, registration_id: int, note: str = "") -> Registration:
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.SUBMITTED,
        to_status=Registration.Status.UNDER_REVIEW,
        note=note,
    )


def approve_registration(
    *, actor, registration_id: int, note: str = ""
) -> Registration:
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.UNDER_REVIEW,
        to_status=Registration.Status.APPROVED,
        note=note,
    )


def reject_registration(*, actor, registration_id: int, note: str) -> Registration:
    if not note.strip():
        raise ValidationError("A rejection reason is required.")
    return _transition_registration(
        actor=actor,
        registration_id=registration_id,
        expected_status=Registration.Status.UNDER_REVIEW,
        to_status=Registration.Status.REJECTED,
        note=note,
    )


def submit_payment_attempt(
    *,
    actor,
    registration_id: int,
    amount: Decimal,
    currency: str,
    proof_file=None,
    reference: str = "",
    registration_access=None,
) -> PaymentAttempt:
    attempt = None
    try:
        with transaction.atomic():
            registration = lock_registration(registration_id)
            if not registration.tournament_game.tournament.is_published:
                raise ValidationError("Tournament is not published.")
            if registration_access is not None:
                authorized = (
                    isinstance(registration_access, RegistrationAccess)
                    and registration_access.pk is not None
                    and RegistrationAccess.objects.filter(
                        pk=registration_access.pk,
                        registration_id=registration.pk,
                        credential_hash=registration_access.credential_hash,
                    ).exists()
                )
            else:
                authorized = (
                    actor is not None
                    and actor.is_authenticated
                    and actor.pk is not None
                    and registration.submitted_by_id == actor.pk
                )
            if not authorized:
                raise PermissionDenied("Only the submitter can add a payment attempt.")
            if registration.fee_amount_snapshot <= Decimal("0.00"):
                raise ValidationError("This registration has no payment due.")
            if amount != registration.fee_amount_snapshot:
                raise ValidationError("Payment amount must match the registration fee.")
            if currency.upper() != registration.fee_currency_snapshot:
                raise ValidationError(
                    "Payment currency must match the registration fee."
                )
            prepared = prepare_payment_image(proof_file)
            # Sanitization may cross the deadline. The authoritative check is after it.
            expire_due_registrations(division_id=registration.tournament_game_id)
            registration.refresh_from_db()
            if is_expired(registration, now=timezone.now()):
                raise ValidationError("Payment reservation has expired.")
            if registration.payment_due_at is not None and (
                registration.status == Registration.Status.REJECTED
                or payment_state(registration) in ("PENDING", "VERIFIED")
            ):
                raise ValidationError(
                    "This registration cannot accept another payment proof."
                )
            attempt = PaymentAttempt(
                registration=registration,
                method=PaymentAttempt.Method.MANUAL_PROOF,
                status=PaymentAttempt.Status.PENDING,
                amount=amount,
                currency=currency.upper(),
                proof_file=prepared,
                reference=reference.strip(),
            )
            attempt.save()
        return attempt
    except Exception:
        if attempt is not None and attempt.proof_file and attempt.proof_file._committed:
            attempt.proof_file.delete(save=False)
        raise


def review_payment_attempt(
    *,
    actor,
    payment_attempt_id: int,
    status: str,
    note: str = "",
) -> PaymentAttempt:
    _require_organizer(actor, "registrations.change_paymentattempt")
    if status not in {PaymentAttempt.Status.VERIFIED, PaymentAttempt.Status.REJECTED}:
        raise ValidationError("A payment attempt may only be verified or rejected.")

    if status == PaymentAttempt.Status.REJECTED and not note.strip():
        raise ValidationError("A rejection reason is required.")
    with transaction.atomic():
        registration_id = PaymentAttempt.objects.values_list(
            "registration_id", flat=True
        ).get(pk=payment_attempt_id)
        registration = lock_registration(registration_id)
        expire_due_registrations(division_id=registration.tournament_game_id)
        registration.refresh_from_db()
        if registration.payment_due_at is not None and (
            is_expired(registration, now=timezone.now())
            or registration.status == Registration.Status.REJECTED
        ):
            raise ValidationError("This registration is no longer active.")
        payment_attempt = PaymentAttempt.objects.select_for_update().get(
            pk=payment_attempt_id
        )
        if payment_attempt.status != PaymentAttempt.Status.PENDING:
            raise ValidationError("Only a pending payment attempt may be reviewed.")
        payment_attempt.status = status
        payment_attempt.reviewed_by = actor
        payment_attempt.reviewed_at = timezone.now()
        payment_attempt.review_note = note.strip()
        payment_attempt.save(
            update_fields=("status", "reviewed_by", "reviewed_at", "review_note")
        )
        if (
            status == PaymentAttempt.Status.REJECTED
            and registration.payment_due_at is not None
            and payment_state(registration) not in ("PENDING", "VERIFIED")
        ):
            registration.payment_due_at = payment_attempt.reviewed_at + timedelta(
                minutes=registration.payment_hold_minutes_snapshot
            )
            registration.save(update_fields=("payment_due_at", "updated_at"))
        return payment_attempt
