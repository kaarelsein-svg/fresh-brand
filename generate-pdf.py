#!/usr/bin/env python3
"""
FRESH. Pitch One-Pager — Pure Python PDF Generator (zero dependencies)
Generates a clean, dark-themed A4 PDF.
"""

import struct
import zlib
import os

class PDFWriter:
    """Minimal PDF writer — no external dependencies."""

    def __init__(self):
        self.objects = []
        self.pages = []
        self.fonts = {}
        self.current_page_stream = []
        self._font_counter = 0

    def _add_object(self, content):
        self.objects.append(content)
        return len(self.objects)  # 1-based obj number

    def add_font(self, name, base_font):
        self._font_counter += 1
        font_name = f"/F{self._font_counter}"
        obj_num = self._add_object(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{base_font} /Encoding /WinAnsiEncoding >>"
        )
        self.fonts[name] = (font_name, obj_num)
        return font_name

    def set_font(self, name, size):
        font_name = self.fonts[name][0]
        self.current_page_stream.append(f"{font_name} {size} Tf")

    def _color_cmd(self, hex_color, stroke=False):
        r = int(hex_color[1:3], 16) / 255
        g = int(hex_color[3:5], 16) / 255
        b = int(hex_color[5:7], 16) / 255
        op = "RG" if stroke else "rg"
        return f"{r:.3f} {g:.3f} {b:.3f} {op}"

    def set_color(self, hex_color):
        self.current_page_stream.append(self._color_cmd(hex_color))

    def set_stroke_color(self, hex_color):
        self.current_page_stream.append(self._color_cmd(hex_color, stroke=True))

    def draw_rect(self, x, y, w, h, fill=True, stroke=False):
        ops = []
        if fill and stroke:
            ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re B")
        elif fill:
            ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        elif stroke:
            ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")
        self.current_page_stream.extend(ops)

    def draw_line(self, x1, y1, x2, y2, width=0.5):
        self.current_page_stream.append(f"{width:.2f} w")
        self.current_page_stream.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def draw_text(self, x, y, text):
        # Escape special PDF characters
        text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        self.current_page_stream.append("BT")
        self.current_page_stream.append(f"{x:.2f} {y:.2f} Td")
        self.current_page_stream.append(f"({text}) Tj")
        self.current_page_stream.append("ET")

    def draw_text_lines(self, x, y, lines, leading):
        self.current_page_stream.append("BT")
        self.current_page_stream.append(f"{x:.2f} {y:.2f} Td")
        self.current_page_stream.append(f"{leading:.2f} TL")
        for i, line in enumerate(lines):
            line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if i == 0:
                self.current_page_stream.append(f"({line}) Tj")
            else:
                self.current_page_stream.append(f"({line}) '")
        self.current_page_stream.append("ET")

    def new_page(self, width=595.28, height=841.89):
        if self.current_page_stream:
            self._finish_page(width, height)
        self.current_page_stream = []
        self._page_w = width
        self._page_h = height

    def _finish_page(self, width, height):
        stream_content = "\n".join(self.current_page_stream)
        stream_bytes = stream_content.encode("latin-1")
        stream_obj = self._add_object(
            f"<< /Length {len(stream_bytes)} >>\nstream\n{stream_content}\nendstream"
        )
        # Build font references
        font_refs = " ".join(
            f"{info[0]} {info[1]} 0 R" for info in self.fonts.values()
        )
        page_obj = self._add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.2f} {height:.2f}] "
            f"/Contents {stream_obj} 0 R /Resources << /Font << {font_refs} >> >> >>"
        )
        self.pages.append(page_obj)

    def save(self, filename):
        # Finish last page
        if self.current_page_stream:
            self._finish_page(self._page_w, self._page_h)

        # Pages object is always obj 2, catalog is obj 1
        # We need to rebuild with catalog and pages at the front

        all_objects = []
        
        # Obj 1: Catalog
        all_objects.append("<< /Type /Catalog /Pages 2 0 R >>")
        
        # Obj 2: Pages
        page_refs = " ".join(f"{p} 0 R" for p in self.pages)
        all_objects.append(
            f"<< /Type /Pages /Kids [{page_refs}] /Count {len(self.pages)} >>"
        )
        
        # Re-number: existing objects start at 3
        # But we already have object numbers based on self.objects list (1-based)
        # We need to shift them by +2
        # Actually, let's just rebuild properly.

        # Simpler approach: write everything sequentially
        output = []
        output.append(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        obj_offsets = []

        def write_obj(num, content):
            obj_offsets.append(len(b"".join(output)))
            data = f"{num} 0 obj\n{content}\nendobj\n".encode("latin-1")
            output.append(data)

        # Catalog
        write_obj(1, "<< /Type /Catalog /Pages 2 0 R >>")

        # Rebuild pages with correct object numbering
        # Fonts start at obj 3
        font_map = {}  # old_obj_num -> new_obj_num
        next_num = 3
        
        for name, (font_name, old_num) in self.fonts.items():
            font_map[old_num] = next_num
            write_obj(next_num, self.objects[old_num - 1])
            next_num += 1

        # Now write streams and pages
        new_page_nums = []
        for old_page_num in self.pages:
            # The page object references a content stream
            page_content = self.objects[old_page_num - 1]
            # Find the content stream reference
            # The content stream is old_page_num - 1 in the objects list
            # Actually let's just get the stream obj num from the page content
            
            # Stream is at old_page_num - 1 (the object before the page)
            stream_old = old_page_num - 1
            stream_new = next_num
            
            # Fix font references in stream content
            stream_data = self.objects[stream_old - 1]
            write_obj(stream_new, stream_data)
            next_num += 1

            # Page object - fix references
            page_data = self.objects[old_page_num - 1]
            # Replace old content ref with new
            page_data = page_data.replace(f"{stream_old} 0 R", f"{stream_new} 0 R")
            # Replace old font refs
            for old_fn, new_fn in font_map.items():
                page_data = page_data.replace(f"{old_fn} 0 R", f"{new_fn} 0 R")
            # Fix parent ref
            page_data = page_data.replace("/Parent 2 0 R", "/Parent 2 0 R")
            
            page_new = next_num
            write_obj(page_new, page_data)
            new_page_nums.append(page_new)
            next_num += 1

        # Now write Pages object (obj 2) 
        page_kids = " ".join(f"{n} 0 R" for n in new_page_nums)
        # We need to insert obj 2 at the right position but we already wrote obj 1
        # Let's write obj 2 now
        pages_content = f"<< /Type /Pages /Kids [{page_kids}] /Count {len(new_page_nums)} >>"
        # Insert after obj 1
        obj2_offset = len(b"".join(output[:2]))  # after header and obj 1
        obj2_data = f"2 0 obj\n{pages_content}\nendobj\n".encode("latin-1")
        output.insert(2, obj2_data)
        
        # Recalculate offsets
        # This is getting complex. Let me use a simpler approach.
        
        # --- RESTART with simple sequential approach ---
        output_simple = bytearray()
        output_simple.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        
        offsets = {}
        obj_counter = [0]

        def w_obj(content_str):
            obj_counter[0] += 1
            num = obj_counter[0]
            offsets[num] = len(output_simple)
            output_simple.extend(f"{num} 0 obj\n{content_str}\nendobj\n".encode("latin-1"))
            return num

        # 1. Catalog (placeholder, will fix)
        cat_num = w_obj("<< /Type /Catalog /Pages PAGESREF >>")

        # 2. Fonts
        font_new_map = {}
        for name, (font_name, old_num) in self.fonts.items():
            new_num = w_obj(self.objects[old_num - 1])
            font_new_map[name] = (font_name, new_num)

        # 3. Streams and Pages
        new_page_nums_2 = []
        font_refs_str = " ".join(f"{info[0]} {info[1]} 0 R" for info in font_new_map.values())
        
        for old_page_num in self.pages:
            stream_old = old_page_num - 1
            stream_content_str = self.objects[stream_old - 1]
            # Fix font names in stream
            for name, (fn, old_n) in self.fonts.items():
                new_fn, new_n = font_new_map[name]
                # Font names in stream are like /F1, should stay same
            stream_num = w_obj(stream_content_str)

            page_content = (
                f"<< /Type /Page /Parent {cat_num + 0} 0 R "  # will fix
                f"/MediaBox [0 0 {self._page_w:.2f} {self._page_h:.2f}] "
                f"/Contents {stream_num} 0 R "
                f"/Resources << /Font << {font_refs_str} >> >> >>"
            )
            # We need Pages obj num. Let's use a placeholder.
            page_num = w_obj(page_content)
            new_page_nums_2.append(page_num)

        # 4. Pages object
        page_kids_str = " ".join(f"{n} 0 R" for n in new_page_nums_2)
        pages_num = w_obj(f"<< /Type /Pages /Kids [{page_kids_str}] /Count {len(new_page_nums_2)} >>")

        # Now fix catalog and page parent references
        output_str = output_simple.decode("latin-1")
        output_str = output_str.replace("PAGESREF", f"{pages_num} 0 R")
        for pn in new_page_nums_2:
            # Fix parent ref - currently points to cat_num + 0, should point to pages_num
            output_str = output_str.replace(
                f"/Parent {cat_num} 0 R", f"/Parent {pages_num} 0 R"
            )
        
        output_final = bytearray(output_str.encode("latin-1"))
        
        # Recalculate offsets from the final output
        final_offsets = {}
        pos = 0
        final_bytes = bytes(output_final)
        while True:
            idx = final_bytes.find(b" 0 obj\n", pos)
            if idx == -1:
                break
            # Find start of line
            line_start = final_bytes.rfind(b"\n", 0, idx)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            obj_num_str = final_bytes[line_start:idx].decode("latin-1").strip()
            try:
                obj_n = int(obj_num_str)
                final_offsets[obj_n] = line_start
            except ValueError:
                pass
            pos = idx + 1

        # Cross-reference table
        xref_offset = len(output_final)
        max_obj = max(final_offsets.keys()) if final_offsets else 0
        
        xref = f"xref\n0 {max_obj + 1}\n"
        xref += "0000000000 65535 f \n"
        for i in range(1, max_obj + 1):
            off = final_offsets.get(i, 0)
            xref += f"{off:010d} 00000 n \n"
        
        output_final.extend(xref.encode("latin-1"))
        
        trailer = (
            f"trailer\n<< /Size {max_obj + 1} /Root {cat_num} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        )
        output_final.extend(trailer.encode("latin-1"))

        with open(filename, "wb") as f:
            f.write(output_final)


def create_pitch_pdf(filename):
    pdf = PDFWriter()

    # Page dimensions (A4 in points)
    W = 595.28
    H = 841.89
    M = 48  # margin

    # Fonts (limited to PDF built-in Type1 fonts)
    pdf.add_font("bold", "Helvetica-Bold")
    pdf.add_font("regular", "Helvetica")
    pdf.add_font("mono", "Courier")
    pdf.add_font("mono-bold", "Courier-Bold")

    pdf.new_page(W, H)

    # ── Background ──
    pdf.set_color("#0a0a0a")
    pdf.draw_rect(0, 0, W, H)

    # ── Top accent line ──
    pdf.set_stroke_color("#c8ff00")
    pdf.draw_line(0, H - 4, W, H - 4, 4)

    # ── Header ──
    y = H - M - 16

    # "FRESH." logo text
    pdf.set_color("#f0f0f0")
    pdf.set_font("bold", 28)
    pdf.draw_text(M, y, "FRESH.")

    # Right side: pitch label
    pdf.set_color("#666666")
    pdf.set_font("mono", 8)
    pdf.draw_text(W - M - 120, y + 10, "PITCH DECK / ONE PAGER")
    pdf.draw_text(W - M - 30, y - 4, "2026")

    # ── Divider ──
    y -= 24
    pdf.set_stroke_color("#333333")
    pdf.draw_line(M, y, W - M, y, 0.5)

    # ── Hero headline ──
    y -= 50
    pdf.set_color("#f0f0f0")
    pdf.set_font("bold", 48)
    pdf.draw_text(M, y, "SPECIALIZE")
    y -= 52
    pdf.draw_text(M, y, "IN NOTHING.")

    # ── Tagline ──
    y -= 28
    pdf.set_color("#999999")
    pdf.set_font("regular", 12)
    pdf.draw_text_lines(M, y, [
        "FRESH. is a creative company built for the unknown.",
        "Sharp minds, great taste, zero limitations."
    ], 16)

    # ── Accent divider ──
    y -= 28
    pdf.set_stroke_color("#c8ff00")
    pdf.draw_line(M, y, M + 200, y, 1.5)
    pdf.set_stroke_color("#1a1a1a")
    pdf.draw_line(M + 200, y, W - M, y, 0.5)

    # ── Two columns: What We Do | Why FRESH. ──
    y -= 28
    col1_x = M
    col2_x = W / 2 + 10

    # Column 1: What We Do
    pdf.set_color("#c8ff00")
    pdf.set_font("mono-bold", 9)
    pdf.draw_text(col1_x, y, "WHAT WE DO")

    services = [
        "Brand Identity & Strategy",
        "Web Design & Development",
        "Campaigns & Advertising",
        "Music & Sound Design",
        "Events & Festivals",
        "Product Design",
        "Art Direction & Curation",
        "Film & Content",
        "Strategy & Consulting",
        "Whatever You Need"
    ]

    pdf.set_color("#e0e0e0")
    pdf.set_font("regular", 10)
    sy = y - 20
    for i, svc in enumerate(services):
        pdf.draw_text(col1_x + 2, sy, svc)
        # subtle line
        pdf.set_stroke_color("#1a1a1a")
        pdf.draw_line(col1_x, sy - 5, col2_x - 20, sy - 5, 0.3)
        sy -= 17

    # Column 2: Why FRESH.
    pdf.set_color("#c8ff00")
    pdf.set_font("mono-bold", 9)
    pdf.draw_text(col2_x, y, "WHY FRESH.")

    reasons = [
        "Multi-disciplinary team, not freelancers",
        "Custom-built team for every project",
        "No templates, no playbooks",
        "Taste combined with technical intelligence",
        "Fresh perspective on every brief",
    ]

    pdf.set_font("regular", 10)
    ry = y - 20
    for reason in reasons:
        pdf.set_color("#c8ff00")
        pdf.draw_text(col2_x, ry, "->")
        pdf.set_color("#cccccc")
        pdf.draw_text(col2_x + 18, ry, reason)
        pdf.set_stroke_color("#1a1a1a")
        pdf.draw_line(col2_x, ry - 5, W - M, ry - 5, 0.3)
        ry -= 17

    # ── Stats Row ──
    y = sy - 20
    stats = [
        ("INF", "DISCIPLINES"),
        ("0", "LIMITATIONS"),
        ("100%", "COMMITMENT"),
        ("1", "STANDARD"),
    ]

    stat_w = (W - 2 * M - 30) / 4
    for i, (val, label) in enumerate(stats):
        sx = M + i * (stat_w + 10)
        # Box background
        pdf.set_color("#111111")
        pdf.draw_rect(sx, y - 10, stat_w, 50)
        # Border
        pdf.set_stroke_color("#222222")
        pdf.draw_rect(sx, y - 10, stat_w, 50, fill=False, stroke=True)
        # Value
        pdf.set_color("#c8ff00")
        pdf.set_font("bold", 22)
        pdf.draw_text(sx + 12, y + 18, val)
        # Label
        pdf.set_color("#666666")
        pdf.set_font("mono", 7)
        pdf.draw_text(sx + 12, y - 2, label)

    # ── Manifesto Block ──
    y -= 36
    # Left accent bar
    pdf.set_color("#c8ff00")
    pdf.draw_rect(M, y - 32, 2.5, 50)
    # Background
    pdf.set_color("#0f0f0f")
    pdf.draw_rect(M + 6, y - 32, W - 2 * M - 6, 50)

    pdf.set_color("#e0e0e0")
    pdf.set_font("regular", 11)
    pdf.draw_text_lines(M + 18, y + 6, [
        '"The future belongs to people who can think across boundaries.',
        'Specialists solve known problems. We take on the ones',
        'nobody\'s figured out yet."'
    ], 15)

    # ── How We Work ──
    y -= 56
    pdf.set_color("#c8ff00")
    pdf.set_font("mono-bold", 9)
    pdf.draw_text(M, y, "HOW WE WORK")

    y -= 20
    steps = [
        ("01", "LISTEN & DECODE", "We uncover the real challenge. Hard questions, honest answers."),
        ("02", "ASSEMBLE & IDEATE", "A purpose-built team for your specific problem. No templates."),
        ("03", "BUILD & DELIVER", "Fast execution, close collaboration. Just the thing, done right."),
    ]

    step_w = (W - 2 * M - 20) / 3
    for i, (num, title, desc) in enumerate(steps):
        bx = M + i * (step_w + 10)
        # Box
        pdf.set_color("#0e0e0e")
        pdf.draw_rect(bx, y - 45, step_w, 65)
        pdf.set_stroke_color("#1a1a1a")
        pdf.draw_rect(bx, y - 45, step_w, 65, fill=False, stroke=True)
        # Number
        pdf.set_color("#c8ff00")
        pdf.set_font("mono", 8)
        pdf.draw_text(bx + 10, y + 8, num)
        # Title
        pdf.set_color("#f0f0f0")
        pdf.set_font("bold", 10)
        pdf.draw_text(bx + 10, y - 8, title)
        # Desc
        pdf.set_color("#999999")
        pdf.set_font("regular", 8)
        # Simple word wrap
        words = desc.split()
        lines = []
        current = ""
        for w in words:
            test = current + " " + w if current else w
            if len(test) * 4.5 < step_w - 20:
                current = test
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)
        pdf.draw_text_lines(bx + 10, y - 24, lines, 11)

    # ── Footer ──
    y = M + 40
    pdf.set_stroke_color("#222222")
    pdf.draw_line(M, y + 20, W - M, y + 20, 0.5)

    # Contact
    pdf.set_color("#c8ff00")
    pdf.set_font("mono-bold", 8)
    pdf.draw_text(M, y + 4, "LET'S TALK")
    pdf.set_color("#f0f0f0")
    pdf.set_font("regular", 10)
    pdf.draw_text(M, y - 10, "hello@fresh.studio")
    pdf.set_color("#666666")
    pdf.set_font("regular", 8)
    pdf.draw_text(M, y - 22, "Remote-first / Worldwide")

    # Online
    pdf.set_color("#c8ff00")
    pdf.set_font("mono-bold", 8)
    pdf.draw_text(W / 2 - 40, y + 4, "ONLINE")
    pdf.set_color("#f0f0f0")
    pdf.set_font("regular", 10)
    pdf.draw_text(W / 2 - 40, y - 10, "fresh.studio")
    pdf.set_color("#666666")
    pdf.set_font("regular", 8)
    pdf.draw_text(W / 2 - 40, y - 22, "@fresh.studio")

    # Tagline
    pdf.set_color("#444444")
    pdf.set_font("regular", 8)
    pdf.draw_text(W - M - 140, y - 4, "Specialize in nothing.")
    pdf.draw_text(W - M - 140, y - 16, "Open to everything.")

    # ── Bottom accent line ──
    pdf.set_stroke_color("#c8ff00")
    pdf.draw_line(0, 2, W, 2, 2)

    pdf.save(filename)
    print(f"PDF saved: {filename}")
    print(f"Size: {os.path.getsize(filename):,} bytes")


if __name__ == "__main__":
    create_pitch_pdf("FRESH-Pitch-OnePager.pdf")
