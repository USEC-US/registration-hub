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
