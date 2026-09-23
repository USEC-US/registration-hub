import type { RegistrationRead } from '$lib/api/types';
import * as m from '$lib/paraglide/messages';

export function paymentStatusMessage({
	payment_state,
	expired,
	status,
	team_name,
	tournament_game
}: Pick<RegistrationRead, 'payment_state' | 'expired' | 'status' | 'team_name'> & {
	tournament_game: Pick<RegistrationRead['tournament_game'], 'tournament_name' | 'game_name'>;
}): string {
	if (expired || status === 'EXPIRED' || status === 'REJECTED') return m.payment_expired();
	if (status === 'APPROVED')
		return m.registration_approved_confirmation({
			tournament: tournament_game.tournament_name,
			tournament_game: tournament_game.game_name,
			team: team_name
		});
	switch (payment_state) {
		case 'PENDING':
			return m.payment_pending_review();
		case 'VERIFIED':
			return m.payment_verified_review();
		case 'NOT_REQUIRED':
			return m.payment_free();
		case 'REJECTED':
			return m.payment_proof_rejected();
		case 'UNPAID':
			return m.payment_unpaid();
	}
}
