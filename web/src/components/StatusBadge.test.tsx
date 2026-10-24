import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JOB_STATES } from "../api/types";
import { STATE_TONES, StatusBadge, stateLabel } from "./StatusBadge";

describe("StatusBadge", () => {
  it("maps every job state to an explicit tone (no fallthrough)", () => {
    for (const s of JOB_STATES) {
      expect(STATE_TONES[s], `tone for ${s}`).toBeDefined();
    }
  });

  it.each(JOB_STATES)("renders Title Case label and tone class for %s", (state) => {
    const { unmount } = render(<StatusBadge state={state} />);
    const el = screen.getByText(stateLabel(state));
    expect(el).toBeInTheDocument();
    expect(el.getAttribute("data-tone")).toBe(STATE_TONES[state]);
    expect(el.className).toMatch(/bg-/);
    unmount();
  });

  it("formats multi-word states", () => {
    expect(stateLabel("completed_with_warnings")).toBe("Completed With Warnings");
    expect(stateLabel("awaiting_approval")).toBe("Awaiting Approval");
  });

  it("uses distinct tones for terminal outcomes", () => {
    expect(STATE_TONES.completed).toBe("green");
    expect(STATE_TONES.completed_with_warnings).toBe("amber");
    expect(STATE_TONES.failed).toBe("red");
    expect(STATE_TONES.cancelled).toBe("slate");
    expect(STATE_TONES.blocked).toBe("violet");
    expect(STATE_TONES.timed_out).toBe("orange");
  });
});
