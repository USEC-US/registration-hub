export type RegistrationState = 'not_open' | 'open' | 'full' | 'closed';
export type RegistrationStatus = 'SUBMITTED' | 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED' | 'EXPIRED';
export type PaymentAttemptStatus = 'PENDING' | 'VERIFIED' | 'REJECTED';
export type PaymentState = 'NOT_REQUIRED' | 'UNPAID' | 'PENDING' | 'VERIFIED' | 'REJECTED';

export interface TokenPair {
	access: string;
	refresh: string;
}

export interface CurrentUser {
	id: number;
	email: string;
	first_name: string;
	last_name: string;
	institution: Institution | null;
}

export interface Institution {
	id: number;
	value: string;
	label: string;
	code: string;
	shortName: string;
	eng: string;
	type: string;
	location: string;
}

export type InstitutionChoice =
	| { institution_id: number; institution_label?: never }
	| { institution_id?: never; institution_label: string };

export type RegisterAccountPayload = {
	email: string;
	password: string;
	first_name: string;
	last_name: string;
} & InstitutionChoice;

export interface PublicTournamentGame {
	id: number;
	game_name: string;
	game_slug: string;
	main_roster_size: number;
	substitute_limit: number;
	registration_opens_at: string;
	registration_closes_at: string;
	registration_capacity: number | null;
	capacity_remaining: number | null;
	fee_amount: string;
	fee_currency: string;
	registration_state: RegistrationState;
	is_registration_open: boolean;
	payment_hold_minutes: number;
	payment_available: boolean;
}

export interface PublicTournament {
	id: number;
	name: string;
	slug: string;
	description: string;
	cover_image: string | null;
	starts_at: string | null;
	ends_at: string | null;
	location: string;
	is_featured: boolean;
	students_only: boolean;
	tournament_games: PublicTournamentGame[];
}

export type CompetitionStageStatus = 'DRAFT' | 'READY' | 'IN_PROGRESS' | 'AWAITING' | 'COMPLETE';
export type CompetitionMatchStatus = 'PENDING' | 'CONDITIONAL' | 'NOT_REQUIRED' | 'LIVE' | 'FINAL';

export interface PublicCompetitionEntry {
	id: number;
	seed: number;
	display_name: string;
	display_tag: string;
}

export interface PublicCompetitionMatchSlot {
	position: 1 | 2;
	is_resolved: boolean;
	is_empty: boolean;
	source_match_id: number | null;
	source_outcome: '' | 'WINNER' | 'LOSER';
	entry: PublicCompetitionEntry | null;
}

export interface PublicCompetitionMatch {
	id: number;
	code: string;
	number: number;
	scheduled_at: string | null;
	status: CompetitionMatchStatus;
	outcome: string;
	effective_series_length: number;
	effective_series_mode: 'BEST_OF' | 'FIXED_GAMES';
	side_one_score: number | null;
	side_two_score: number | null;
	started_at: string | null;
	completed_at: string | null;
	historical: boolean;
	winner: PublicCompetitionEntry | null;
	slots: PublicCompetitionMatchSlot[];
}

export interface PublicCompetitionRound {
	id: number;
	number: number;
	section: string;
	group_id: number | null;
	tie_resolution_id: number | null;
	effective_series_mode: 'BEST_OF' | 'FIXED_GAMES';
	resting_entry: PublicCompetitionEntry | null;
	series_length_override: number | null;
	matches: PublicCompetitionMatch[];
}

export interface PublicCompetitionStage {
	id: number;
	sequence: number;
	name: string;
	format: string;
	grand_final_policy: '' | 'RESET' | 'NO_RESET';
	series_mode: string;
	default_series_length: number;
	status: CompetitionStageStatus;
	published_at: string;
	completed_at: string | null;
	completed_without_champion: boolean;
	champion: Pick<PublicCompetitionEntry, 'id' | 'display_name' | 'display_tag'> | null;
	entries: PublicCompetitionEntry[];
	rounds: PublicCompetitionRound[];
	groups: PublicCompetitionGroup[];
	round_robin_rules: {
		meetings: 1 | 2;
		win_points: string;
		draw_points: string;
		loss_points: string;
		tiebreaks: string[];
	} | null;
}

export interface PublicCompetitionStanding {
	entry: PublicCompetitionEntry;
	rank: number;
	played: number;
	wins: number;
	draws: number;
	losses: number;
	points: string;
	games_won: number;
	game_difference: number;
	qualification: 'PROVISIONAL' | 'TIED' | 'QUALIFIED' | 'NOT_QUALIFIED';
}

export interface PublicCompetitionGroup {
	id: number;
	number: number;
	name: string;
	qualifying_places: number;
	entries: PublicCompetitionEntry[];
	round_ids: number[];
	standings: PublicCompetitionStanding[];
	qualifiers: PublicCompetitionEntry[];
	qualification_state: 'PROVISIONAL' | 'AWAITING_RESOLUTION' | 'RESOLVED';
	tie_resolutions: Array<{
		id: number;
		parent_id: number | null;
		method: 'MANUAL' | 'EXTRA_MATCHES';
		state: 'PENDING' | 'AWAITING_RESOLUTION' | 'CONFIRMED' | 'SUPERSEDED';
		tied_entries: PublicCompetitionEntry[];
		places: number;
		ordered_entries: PublicCompetitionEntry[];
		round_ids: number[];
	}>;
}

export interface PublicCompetition {
	id: number;
	competition_revision: number;
	tournament_game_id: number;
	tournament_slug: string;
	tournament_name: string;
	game_name: string;
	stages: PublicCompetitionStage[];
}

export interface PublicCompetitionChange {
	revision: number;
	created_at: string;
	kind: string;
	match_id?: number;
	match_code?: string;
	scheduled_at?: string | null;
	side_one_score?: number | null;
	side_two_score?: number | null;
	winner?: string | null;
	group_name?: string;
	method?: 'MANUAL' | 'EXTRA_MATCHES';
	tied_entries?: string[];
	ordered_entries?: string[];
	group_impact?: {
		group_id: number;
		group_name: string;
		invalidated_resolution_ids: number[];
		revalidated_resolution_ids: number[];
		before: {
			qualifiers: number[];
			qualification_state: string;
			standings: Array<
				Omit<PublicCompetitionStanding, 'entry' | 'qualification'> & { entry_id: number }
			>;
		};
		after: {
			qualifiers: number[];
			qualification_state: string;
			standings: Array<
				Omit<PublicCompetitionStanding, 'entry' | 'qualification'> & { entry_id: number }
			>;
		};
		historical_matches: PublicCompetitionMatchSnapshot[];
	};
	before?: PublicCompetitionMatchSnapshot;
	after?: PublicCompetitionMatchSnapshot;
	reset_matches?: PublicCompetitionMatchSnapshot[];
	reset_final_changes?: Array<{
		match_id: number;
		match_code: string;
		before: 'ACTIVE' | 'CONDITIONAL' | 'NOT_REQUIRED';
		after: 'ACTIVE' | 'CONDITIONAL' | 'NOT_REQUIRED';
	}>;
}

export interface PublicCompetitionMatchSnapshot {
	match_id: number;
	match_code: string;
	status: CompetitionMatchStatus;
	outcome: string;
	side_one: string | null;
	side_two: string | null;
	side_one_score: number | null;
	side_two_score: number | null;
	winner: string | null;
	applied_series_length: number | null;
	applied_series_mode?: 'BEST_OF' | 'FIXED_GAMES' | '';
	started_at: string | null;
	completed_at: string | null;
}

export interface PublicCompetitionChangesPage {
	next: string | null;
	previous: string | null;
	results: PublicCompetitionChange[];
	competition_revision: number;
}

export type RosterRole = 'main' | 'substitute';

export interface RegistrationMemberRead {
	gamer_tag_snapshot: string;
	school_snapshot: string;
	is_captain: boolean;
	roster_role: RosterRole;
	display_order: number;
}

export type RegistrationMemberInput = Omit<RegistrationMemberRead, 'school_snapshot'> &
	InstitutionChoice & {
		first_name_snapshot: string;
		last_name_snapshot: string;
		date_of_birth_snapshot: string;
		student_id_snapshot: string;
	};
export type SubmitterRole = 'captain' | 'manager';

export interface RegistrationSubmissionPayload {
	payment_intent_token?: string;
	tournament_game: number;
	team_name: string;
	team_tag: string;
	submitter_role: SubmitterRole;
	contact_facebook_snapshot: string;
	contact_phone_snapshot: string;
	contact_email_snapshot?: string;
	contact_discord_snapshot?: string;
	manager_name_snapshot?: string;
	members: RegistrationMemberInput[];
}

export interface RegistrationRead {
	id: number;
	tournament_game: {
		id: number;
		tournament_name: string;
		game_name: string;
		main_roster_size: number;
		substitute_limit: number;
		fee_amount: string;
		fee_currency: string;
	};
	team_name: string;
	team_tag: string;
	status: RegistrationStatus;
	fee_amount_snapshot: string;
	fee_currency_snapshot: string;
	submitted_at: string;
	payment_required: boolean;
	payment_reference: string;
	payment_state: PaymentState;
	payment_due_at: string | null;
	expired: boolean;
	members: RegistrationMemberRead[];
	status_events: { to_status: RegistrationStatus; created_at: string }[];
	payment_attempts: {
		id: number;
		status: PaymentAttemptStatus;
		amount: string;
		currency: string;
		created_at: string;
	}[];
}

export interface RegistrationPaymentInstructions {
	bank_name: string;
	bank_bin: string;
	account_number: string;
	account_holder: string;
	amount: string;
	currency: string;
	transfer_content: string;
	transfer_content_limit: number;
	qr_payload: string | null;
	qr_png_data_url: string | null;
	qr_contains_transfer_content: boolean;
}

export interface RegistrationPaymentSession {
	readonly tournament_slug: string;
	registration: RegistrationRead;
	payment_state: PaymentState;
	payment_due_at: string | null;
	server_now: string;
	expired: boolean;
	can_upload_proof: boolean;
	can_retry_registration: boolean;
	replacement_note: string;
	saved_submission: RegistrationSubmissionPayload;
	institution_labels: Record<string, string>;
	instructions: RegistrationPaymentInstructions | null;
}
