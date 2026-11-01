import { render, screen } from "@testing-library/react";
import { money, dateOnly } from "./lib/format";
import { CheckBadge } from "./components/ui";

test("money formats decimal strings without floating drift and keeps unknowns null", () => {
  expect(money("570.00", "USD")).toBe("$570.00");
  expect(money("1234.5", "EUR")).toBe("€1,234.50");
  expect(money(null, "USD")).toBeNull();
});

test("dates render without timezone shift", () => {
  expect(dateOnly("2026-11-08")).toBe("8 Nov 2026");
});

test("check badges never rely on colour alone", () => {
  render(<><CheckBadge status="pass" /><CheckBadge status="fail" /><CheckBadge status="unknown" /></>);
  expect(screen.getByText("Pass")).toBeInTheDocument();
  expect(screen.getByText("Fail")).toBeInTheDocument();
  expect(screen.getByText("Unknown")).toBeInTheDocument();
});

import { csvSafe } from "./components/CompareStep";
test("CSV export neutralises spreadsheet formulas from supplier text", () => {
  expect(csvSafe("=HYPERLINK(\"http://x\")")).toBe("'=HYPERLINK(\"http://x\")");
  expect(csvSafe("+1+1")).toBe("'+1+1");
  expect(csvSafe("@SUM(A1)")).toBe("'@SUM(A1)");
  expect(csvSafe("ClearWave Supplies")).toBe("ClearWave Supplies");
  expect(csvSafe(570)).toBe("570");
});
