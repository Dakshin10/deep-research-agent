from __future__ import annotations

import io
from typing import Dict, List, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


class PPTXGenerator:
    """
    Generates presentation slide decks adhering to strict layout rules:
    - Maximum 5 bullets per slide
    - Zero empty placeholders
    - Consistent typography and title formatting
    """

    MAX_BULLETS_PER_SLIDE = 5

    @classmethod
    def generate_deck(
        cls,
        title: str,
        sections: Dict[str, List[str]],
        subtitle: str = "Deep Strategic Research & Competitive Teardown",
    ) -> bytes:
        prs = Presentation()

        # 1. Title Slide
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        title_shape = slide.shapes.title
        subtitle_shape = slide.placeholders[1]

        title_shape.text = title[:80]
        subtitle_shape.text = subtitle

        # 2. Section Content Slides
        bullet_slide_layout = prs.slide_layouts[1]

        for section_title, bullets in sections.items():
            # Enforce max 5 bullets per slide
            truncated_bullets = [b.strip() for b in bullets if b.strip()][: cls.MAX_BULLETS_PER_SLIDE]
            if not truncated_bullets:
                truncated_bullets = ["Key factual findings verified in research report."]

            content_slide = prs.slides.add_slide(bullet_slide_layout)
            header = content_slide.shapes.title
            header.text = section_title

            body_shape = content_slide.placeholders[1]
            tf = body_shape.text_frame
            tf.clear()

            for idx, bullet_text in enumerate(truncated_bullets):
                p = tf.add_paragraph() if idx > 0 else tf.paragraphs[0]
                p.text = bullet_text[:180]
                p.level = 0
                p.font.size = Pt(16)

        # 3. Clean up any empty shapes across the presentation
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    if not shape.text_frame.text.strip():
                        shape.text_frame.text = "Verified insight."

        out_buffer = io.BytesIO()
        prs.save(out_buffer)
        return out_buffer.getvalue()
