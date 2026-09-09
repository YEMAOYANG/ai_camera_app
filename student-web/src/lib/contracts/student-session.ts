import { z } from "zod";

export const studentSchema = z.object({
  id: z.string().min(1),
  childId: z.string().min(1),
  displayName: z.string().min(1),
  gradeCode: z.string().nullable().optional(),
  gradeLabel: z.string().nullable().optional(),
});

export const studentDeviceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  trustedUntil: z.number().positive().optional(),
  lastActiveAt: z.number().nullable().optional(),
});

export const tokenSchema = z.object({
  accessToken: z.string().min(1),
  refreshToken: z.string().min(1),
  accessTokenExpiresAt: z.number(),
  refreshTokenExpiresAt: z.number(),
  expiresInSeconds: z.number().positive(),
});

export const studentAuthResponseSchema = z.object({
  ok: z.literal(true),
  student: studentSchema,
  device: studentDeviceSchema,
  tokens: tokenSchema,
  deviceToken: z.string().min(1).optional(),
});

export const studentQrAuthResponseSchema = studentAuthResponseSchema.extend({
  deviceToken: z.string().min(1),
});

export const studentMeResponseSchema = z.object({
  ok: z.literal(true),
  student: studentSchema,
  device: studentDeviceSchema,
});

export const studentQrChallengeIdSchema = z.string().regex(/^msc_[A-Za-z0-9_-]{40,96}$/);
export const studentQrVerifierSchema = z.string().regex(/^msv_[A-Za-z0-9_-]{40,96}$/);
export const studentQrDisplayCodeSchema = z.string().regex(/^\d{4}$/);
export const studentQrPollingIntervalSchema = z.number().int().min(250);

export const studentQrChallengeSchema = z.object({
  challengeId: studentQrChallengeIdSchema,
  verifier: studentQrVerifierSchema,
  displayCode: studentQrDisplayCodeSchema,
  expiresAt: z.number().positive(),
  pollingIntervalMs: studentQrPollingIntervalSchema,
});

export const studentQrStartResponseSchema = z.object({
  ok: z.literal(true),
  qrValue: z.string().url(),
  displayCode: studentQrDisplayCodeSchema,
  expiresAt: z.number().positive(),
  pollingIntervalMs: studentQrPollingIntervalSchema,
});

export const backendErrorSchema = z.object({
  ok: z.literal(false).optional(),
  error: z.string().optional(),
  message: z.string().optional(),
});

export type Student = z.infer<typeof studentSchema>;
export type StudentAuthResponse = z.infer<typeof studentAuthResponseSchema>;
export type StudentQrAuthResponse = z.infer<typeof studentQrAuthResponseSchema>;
export type StudentQrChallenge = z.infer<typeof studentQrChallengeSchema>;
export type StudentQrStartResponse = z.infer<typeof studentQrStartResponseSchema>;
