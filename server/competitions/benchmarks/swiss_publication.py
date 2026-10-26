"""Persisted 256-entry/64-round publication proof; run as a Django shell script.

    python manage.py shell < competitions/benchmarks/swiss_publication.py

Creates and removes only its UUID-named local PostgreSQL database. Historical
setup uses production pairings/persistence and bulk 1-1 results, not 8064 score
commands. Run without competing tests/builds; this is not a latency guarantee.
"""

import json
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from django.core.management import call_command
from django.db import connection, connections, transaction
from django.utils import timezone

from competitions import swiss_commands as swiss
from competitions.command_support import _record_change
from competitions.models import Match
from competitions.tests.test_swiss_commands import SwissCommandTests


def measure():
    config = connection.settings_dict
    if connection.vendor != "postgresql" or config["HOST"] not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        raise RuntimeError(
            "Use an explicitly disposable local PostgreSQL configuration."
        )
    original_name = config["NAME"]
    database = "swiss_publication_" + uuid4().hex
    admin = psycopg.connect(
        dbname=original_name,
        user=config["USER"],
        password=config["PASSWORD"],
        host=config["HOST"],
        port=config["PORT"],
        autocommit=True,
    )
    created = False
    try:
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(
                sql.Identifier(database)
            )
        )
        created = True
        print(f"Created benchmark database {database}", flush=True)
        connection.close()
        config["NAME"] = database
        call_command("migrate", verbosity=0, interactive=False)
        started = perf_counter()
        fixture = SwissCommandTests()
        fixture.setUp()
        draw = fixture._draw(
            256, round_count=64, series_mode="FIXED_GAMES", default_series_length=2
        )
        fixture._revision()
        round_ = draw.rounds.get(number=1)
        seen_pairs = set()
        for number in range(1, 64):
            with transaction.atomic():
                round_.matches.update(
                    status="FINAL",
                    outcome="PLAYED",
                    side_one_score=1,
                    side_two_score=1,
                    winner=None,
                    applied_series_mode="FIXED_GAMES",
                    applied_series_length=2,
                    started_at=timezone.now(),
                    completed_at=timezone.now(),
                )
                results = swiss._swiss_results(draw)
                pairing = swiss.pair_swiss_round(
                    dict(draw.entries.values_list("pk", "seed")),
                    swiss._rank(draw, results),
                    results,
                    format=draw.stage.format,
                )
                assert len(pairing.pairs) == 128 and not pairing.repeat_pairs
                pairs = {tuple(sorted(pair)) for pair in pairing.pairs}
                assert not seen_pairs.intersection(pairs)
                seen_pairs.update(pairs)
                round_ = swiss._persist_swiss_round(
                    draw,
                    number=number + 1,
                    pairing=pairing,
                    source_fingerprint=swiss._swiss_source_fingerprint(
                        draw, number + 1
                    ),
                    rematches_authorized=False,
                )
                _record_change(
                    fixture.competition,
                    actor=fixture.actor,
                    kind="swiss_round_saved",
                    private_data={
                        "draw_id": draw.pk,
                        "stage_id": draw.stage_id,
                        "swiss_round": swiss._swiss_round_payload(round_),
                        "repeat_pairs": [],
                        "cross_group_pairs": [
                            list(p) for p in pairing.cross_group_pairs
                        ],
                    },
                )
                if number < 63:
                    round_.state = "PUBLISHED"
                    round_.published_at = timezone.now()
                    round_.save(update_fields=("state", "published_at"))
                    _record_change(
                        fixture.competition,
                        actor=fixture.actor,
                        kind="swiss_round_published",
                        private_data={"round_id": round_.pk},
                        public_data={
                            "kind": "swiss_round_published",
                            "stage_id": draw.stage_id,
                            **swiss._swiss_public_round(round_),
                        },
                    )
            if number % 8 == 0:
                print(f"Saved round {number + 1}/64", flush=True)
        setup_seconds = perf_counter() - started
        assert draw.entries.count() == 256 and draw.swiss_round_limit == 64
        assert draw.rounds.filter(state="PUBLISHED").count() == 63
        assert Match.objects.filter(round__draw=draw).count() == 8192
        historical = Match.objects.filter(round__draw=draw, status="FINAL").order_by(
            "pk"
        )
        before = list(historical.values())
        assert len(before) == 8064
        revision = fixture._revision()
        history = list(fixture.competition.changes.order_by("revision").values())
        counters = {"sql": 0, "solver_calls": 0, "solver_seconds": 0.0}
        solver = swiss.pair_swiss_round

        def counted_solver(*args, **kwargs):
            counters["solver_calls"] += 1
            start = perf_counter()
            try:
                return solver(*args, **kwargs)
            finally:
                counters["solver_seconds"] += perf_counter() - start

        def counted_sql(execute, query, params, many, context):
            counters["sql"] += 1
            return execute(query, params, many, context)

        with (
            patch.object(swiss, "pair_swiss_round", counted_solver),
            connection.execute_wrapper(counted_sql),
        ):
            start = perf_counter()
            swiss.publish_swiss_round(
                actor=fixture.actor, round_id=round_.pk, expected_revision=revision
            )
            publication_seconds = perf_counter() - start
        round_.refresh_from_db()
        assert (
            round_.state == "PUBLISHED"
            and round_.matches.filter(status="PENDING").count() == 128
        )
        assert counters["solver_calls"] == 1
        assert before == list(historical.values())
        assert fixture._revision() == revision + 1
        assert history == list(
            fixture.competition.changes.filter(revision__lte=revision)
            .order_by("revision")
            .values()
        )
        event = fixture.competition.changes.get(revision=revision + 1)
        assert (
            event.kind == "swiss_round_published"
            and event.public_data["round_number"] == 64
        )
        print(
            json.dumps(
                {
                    "database": database,
                    "setup_seconds": setup_seconds,
                    "publication_seconds": publication_seconds,
                    **counters,
                    "entries": 256,
                    "rounds": 64,
                    "historical_matches": len(before),
                    "state": round_.state,
                    "revision": revision + 1,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    finally:
        connections.close_all()
        config["NAME"] = original_name
        if created:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
            print(f"Removed only benchmark database {database}", flush=True)
        admin.close()


measure()
