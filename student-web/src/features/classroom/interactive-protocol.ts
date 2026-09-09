import { z } from "zod";

export const miraWidgetProtocol = "mira.widget.v1" as const;

export const widgetMessageSchema = z.object({
  protocol: z.literal(miraWidgetProtocol),
  sceneId: z.string().min(1).max(160),
  kind: z.enum(["ready", "progress", "complete", "error"]),
  payload: z.record(z.string(), z.unknown()).optional(),
});

export type WidgetMessage = z.infer<typeof widgetMessageSchema>;

