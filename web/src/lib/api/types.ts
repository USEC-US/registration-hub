export type RegistrationState = 'not_open' | 'open' | 'full' | 'closed';
export type RegistrationStatus = 'SUBMITTED' | 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED';
export type PaymentAttemptStatus = 'PENDING' | 'VERIFIED' | 'REJECTED';

export interface TokenPair {
	access: string;
	refresh: string;
}

export interface CurrentUser {
	id: number;
	email: string;
	first_name: string;
	last_name: string;
	school: string;
}

export interface PublicTournamentGame {
	id: number;
	game_name: string;
	game_slug: string;
	team_size_min: number;
	team_size_max: number;
	registration_opens_at: string;
	registration_closes_at: string;
	registration_capacity: number | null;
	capacity_remaining: number | null;
	fee_amount: string;
	fee_currency: string;
	registration_state: RegistrationState;
	is_registration_open: boolean;
}

export interface PublicTournament {
	id: number;
	name: string;
	slug: string;
	description: string;
	starts_at: string | null;
	ends_at: string | null;
	location: string;
	tournament_games: PublicTournamentGame[];
}

export interface RegistrationMemberInput {
	gamer_tag_snapshot: string;
	school_snapshot: string;
	is_captain: boolean;
	display_order: number;
}

export interface RegistrationSubmissionPayload {
	tournament_game: number;
	team_name: string;
	members: RegistrationMemberInput[];
}

export interface RegistrationRead {
	id: number;
	tournament_game: {
		id: number;
		tournament_name: string;
		game_name: string;
		team_size_min: number;
		team_size_max: number;
		fee_amount: string;
		fee_currency: string;
	};
	team_name: string;
	status: RegistrationStatus;
	fee_amount_snapshot: string;
	fee_currency_snapshot: string;
	submitted_at: string;
	payment_required: boolean;
	members: RegistrationMemberInput[];
	status_events: { to_status: RegistrationStatus; created_at: string }[];
	payment_attempts: {
		id: number;
		status: PaymentAttemptStatus;
		amount: string;
		currency: string;
		created_at: string;
	}[];
}
