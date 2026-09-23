import { describe, expect, it } from 'vitest';
import { overwriteGetLocale } from '$lib/paraglide/runtime';
import { paymentStatusMessage } from './payment-status';

describe('payment status message', () => {
	it('reports registration approval after staff approves a verified paid registration', () => {
		overwriteGetLocale(() => 'en');
		const registration = {
			payment_state: 'VERIFIED' as const,
			expired: false,
			status: 'APPROVED' as const,
			team_name: 'Blue Team',
			tournament_game: { tournament_name: 'USEC Summer 2026', game_name: 'Valorant' }
		};
		expect(paymentStatusMessage(registration)).toBe(
			'The registration for team Blue Team in USEC Summer 2026 - Valorant has been confirmed! Thank you for your interest in USEC tournaments!'
		);
		expect(paymentStatusMessage({ ...registration, status: 'UNDER_REVIEW' })).toBe(
			'Payment verified. Eligibility approval is a separate organizer decision.'
		);
		overwriteGetLocale(() => 'vi');
		expect(paymentStatusMessage(registration)).toBe(
			'Bản đăng ký giải đấu USEC Summer 2026 - bộ môn Valorant của đội Blue Team đã được xác nhận! Cảm ơn đã quan tâm theo dỗi với các giải đấu của USEC!'
		);
	});
});
