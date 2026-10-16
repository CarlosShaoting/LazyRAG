import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as XLSX from "xlsx";

const previewState = vi.hoisted(() => ({ calls: 0 }));

vi.mock("@/i18n", () => ({ default: { t: (key: string) => key } }));
vi.mock("@js-preview/excel", () => ({
  default: {
    init: (container: HTMLElement, options: { transformData: (data: unknown[]) => unknown[] }) => ({
      destroy: vi.fn(),
      preview: vi.fn(async () => {
        previewState.calls += 1;
        if (previewState.calls === 1) {
          options.transformData([{ name: "Orders", rows: {} }]);
          return;
        }
        options.transformData([{
          name: "Orders",
          rows: { 0: { cells: { 0: { text: "Item" } } } },
        }]);
        container.textContent = "Item";
      }),
    }),
  },
}));

import RenderExcel from "./render-excel";

describe("Excel preview compatibility", () => {
  it("normalizes and retries a valid XLSX that initially renders as an empty grid", async () => {
    previewState.calls = 0;
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.aoa_to_sheet([["Item"], ["Alpha"]]),
      "Orders",
    );
    const fileData = XLSX.write(workbook, {
      type: "array",
      bookType: "xlsx",
    }) as ArrayBuffer;

    render(
      <RenderExcel
        fileData={fileData}
        fileType="excel"
        content={null}
        metadata={null}
      />,
    );

    expect(await screen.findByText("Item")).toBeInTheDocument();
    await waitFor(() => expect(previewState.calls).toBe(2));
  });
});
