import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PairingForm } from "@/features/auth/pairing-form";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

vi.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    span: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
    div: (props: React.HTMLAttributes<HTMLDivElement> & { initial?: unknown }) => {
      const domProps = { ...props };
      delete domProps.initial;
      return <div {...domProps} />;
    },
  },
  useReducedMotion: () => true,
}));

vi.mock("@/features/auth/qr-pairing", () => ({
  QrPairing: () => <div>扫码登录入口</div>,
}));

describe("PairingForm", () => {
  beforeEach(() => {
    replace.mockReset();
    refresh.mockReset();
  });

  it("requires a complete 8-character pairing code", () => {
    render(<PairingForm />);
    expect(screen.getByLabelText("8位配对码")).not.toBeVisible();
    fireEvent.click(screen.getByText("无法扫码？使用配对码"));
    expect(screen.getByLabelText("8位配对码")).toBeVisible();
    const submit = screen.getByRole("button", { name: "进入学习空间" });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("8位配对码"), { target: { value: "ab12-cd34" } });
    expect(screen.getByLabelText("8位配对码")).toHaveValue("AB12 CD34");
    expect(submit).toBeEnabled();
  });
});
