package doc

import "testing"

func TestNeedsOfficeConvertBeforeParse(t *testing.T) {
	pptExt := documentExt{
		StoredPath:       "/data/demo.pptx",
		OriginalFilename: "demo.pptx",
		ContentType:      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
		ConvertRequired:  true,
	}
	docExt := documentExt{
		StoredPath:       "/data/demo.docx",
		OriginalFilename: "demo.docx",
		ContentType:      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		ConvertRequired:  true,
	}
	xlsxExt := documentExt{
		StoredPath:       "/data/demo.xlsx",
		OriginalFilename: "demo.xlsx",
		ContentType:      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		ConvertRequired:  true,
	}
	mineruCfg := map[string]any{"ocr_type": "mineru", "ocr_url": "https://mineru.net"}
	paddleCfg := map[string]any{"ocr_type": "paddleocr", "ocr_url": "http://paddle:8000"}

	tests := []struct {
		name      string
		doc       documentExt
		ocrConfig map[string]any
		want      bool
	}{
		{"ppt with mineru skips convert", pptExt, mineruCfg, false},
		{"ppt with paddle converts", pptExt, paddleCfg, true},
		{"ppt without ocr config converts", pptExt, nil, true},
		{"docx with mineru still converts", docExt, mineruCfg, true},
		{"xlsx always converts", xlsxExt, paddleCfg, true},
		{"xlsx with mineru still converts", xlsxExt, mineruCfg, true},
		{"non-office never converts", documentExt{StoredPath: "/data/demo.pdf", ConvertRequired: false}, mineruCfg, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := needsOfficeConvertBeforeParse(tt.doc, tt.ocrConfig); got != tt.want {
				t.Fatalf("needsOfficeConvertBeforeParse() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestParsePathForIngestionPresentationMineru(t *testing.T) {
	d := documentExt{
		StoredPath:       "/data/demo.pptx",
		ParseStoredPath:  "/data/demo.pdf",
		OriginalFilename: "demo.pptx",
		ConvertRequired:  true,
	}
	cfg := map[string]any{"ocr_type": "mineru"}
	if got := parsePathForIngestion(d, cfg); got != "/data/demo.pptx" {
		t.Fatalf("parsePathForIngestion() = %q, want original pptx path", got)
	}
}

func TestNewDocumentExtSpreadsheetRequiresConvert(t *testing.T) {
	d := newDocumentExt("/data/demo.xlsx", "demo.xlsx", "demo.xlsx", 100, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "", nil)
	if !d.ConvertRequired {
		t.Fatal("xlsx upload should require office conversion")
	}
	if d.ConvertStatus != ConvertStatusPending {
		t.Fatalf("xlsx ConvertStatus = %q, want %q", d.ConvertStatus, ConvertStatusPending)
	}
}

func TestParsePathForIngestionSpreadsheet(t *testing.T) {
	d := documentExt{
		StoredPath:       "/data/demo.xlsx",
		ParseStoredPath:  "/data/demo.pdf",
		OriginalFilename: "demo.xlsx",
		ConvertRequired:  true,
	}
	if got := parsePathForIngestion(d, nil); got != "/data/demo.pdf" {
		t.Fatalf("parsePathForIngestion() = %q, want converted pdf path", got)
	}
}

func TestParsePathForIngestionPresentationPaddle(t *testing.T) {
	d := documentExt{
		StoredPath:       "/data/demo.pptx",
		ParseStoredPath:  "/data/demo.pdf",
		OriginalFilename: "demo.pptx",
		ConvertRequired:  true,
	}
	cfg := map[string]any{"ocr_type": "paddleocr"}
	if got := parsePathForIngestion(d, cfg); got != "/data/demo.pdf" {
		t.Fatalf("parsePathForIngestion() = %q, want converted pdf path", got)
	}
}
