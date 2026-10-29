"""
title: CSEEC Assessment Export
description: Create separate student, teacher and Microsoft Forms import Word files locally.
author: CSEEC
version: 0.1.0
license: MIT
"""

import asyncio
import hashlib
from io import BytesIO
import json
import re
from uuid import uuid4

_GATE = asyncio.Semaphore(1)
MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def clean(value, maximum=6000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Text field missing, invalid or too long")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
        raise ValueError("Unsupported control character")
    return value.strip()


def validate(exam_json):
    if not isinstance(exam_json, str) or len(exam_json.encode("utf-8")) > 160000:
        raise ValueError("Assessment input must be at most 160000 UTF-8 bytes")
    data = json.loads(exam_json)
    if not isinstance(data, dict):
        raise ValueError("Assessment must be a JSON object")
    for key in ("title", "course", "language"):
        data[key] = clean(data.get(key), 240)
        if not data[key]:
            raise ValueError("Title, course and language are required")
    if type(data.get("grade")) is not int or data["grade"] not in range(8, 13):
        raise ValueError("Grade must be an integer from 8 to 12")
    minutes = data.get("duration_minutes", 45)
    if type(minutes) is not int or not 5 <= minutes <= 240:
        raise ValueError("Duration must be 5 to 240 minutes")
    data["duration_minutes"] = minutes
    data["instructions"] = clean(data.get("instructions", ""), 3000)
    questions = data.get("questions")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 40:
        raise ValueError("Use 1 to 40 questions per file")
    stems = set()
    for index, question in enumerate(questions, 1):
        if not isinstance(question, dict) or question.get("type") not in (
            "multiple_choice",
            "open_text",
        ):
            raise ValueError("Only multiple_choice and open_text are supported")
        question["stem"] = clean(question.get("stem"))
        normalized = " ".join(question["stem"].casefold().split())
        if not normalized or normalized in stems:
            raise ValueError("Empty or duplicate question stem")
        stems.add(normalized)
        points = question.get("points", 1)
        if type(points) is not int or not 1 <= points <= 30:
            raise ValueError("Points must be an integer from 1 to 30")
        question["points"] = points
        for key in (
            "answer",
            "explanation",
            "objective",
            "source_reference",
            "rubric",
            "common_error",
        ):
            question[key] = clean(question.get(key, ""))
        if not question["explanation"] or not question["objective"]:
            raise ValueError(
                "Each question needs an explanation and learning objective"
            )
        question["difficulty"] = clean(question.get("difficulty", "application"), 80)
        if question["type"] == "multiple_choice":
            options = question.get("options")
            answers = question.get("correct_option_indices")
            if not isinstance(options, list) or not 2 <= len(options) <= 6:
                raise ValueError("Choice questions require 2 to 6 options")
            question["options"] = [clean(option, 1500) for option in options]
            normalized_options = [
                option.casefold().strip() for option in question["options"]
            ]
            if any(not option for option in normalized_options) or len(
                set(normalized_options)
            ) != len(options):
                raise ValueError("Options must be nonempty and unique")
            if (
                not isinstance(answers, list)
                or not answers
                or any(
                    type(a) is not int or a not in range(len(options)) for a in answers
                )
                or len(set(answers)) != len(answers)
            ):
                raise ValueError(
                    "Correct option indices must be unique valid zero-based integers"
                )
        elif not question["answer"] or not question["rubric"]:
            raise ValueError(
                "Open text questions require a reference answer and marking rubric"
            )
        lines = question.get("working_lines", 4)
        if type(lines) is not int or not 0 <= lines <= 12:
            raise ValueError("Working lines must be 0 to 12")
        question["working_lines"] = lines
        question["number"] = index
    data["total_points"] = sum(question["points"] for question in questions)
    return data


def build_documents(data):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    def base(title):
        doc = Document()
        section = doc.sections[0]
        section.page_width, section.page_height = Inches(8.5), Inches(11)
        section.top_margin = section.bottom_margin = Inches(0.7)
        section.left_margin = section.right_margin = Inches(0.8)
        for style_name in ("Normal", "Title", "Heading 1", "Heading 2"):
            style = doc.styles[style_name]
            style.font.name = "Arial"
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.font.size = Pt(11 if style_name == "Normal" else 16)
            style.element.get_or_add_rPr().rFonts.set(
                qn("w:eastAsia"), "Microsoft YaHei"
            )
        doc.styles["Normal"].paragraph_format.space_after = Pt(7)
        doc.styles["Normal"].paragraph_format.line_spacing = 1.12
        doc.core_properties.author = "CSEEC"
        doc.core_properties.title = title
        doc.add_paragraph(title, "Title")
        doc.add_paragraph(
            f"{data['course']} | Grade {data['grade']} | {data['language']}"
        )
        return doc

    student = base(data["title"])
    student.add_paragraph(
        f"Name / 姓名 ____________________   Date / 日期 ______________"
    )
    student.add_paragraph(
        f"Time / 时间 {data['duration_minutes']} min    Total / 总分 {data['total_points']}"
    )
    if data["instructions"]:
        student.add_paragraph(data["instructions"])
    teacher = base(data["title"] + " Answer Key")
    teacher.add_paragraph(
        f"Total / 总分 {data['total_points']} | Teacher use only / 仅供教师"
    )
    forms = base(data["title"])
    # Plain vertical layout; no answers, rubrics, answer spaces or point annotations.
    for question in data["questions"]:
        number = question["number"]
        stem = question["stem"]
        para = student.add_paragraph(f"{number}. {stem}  [{question['points']} points]")
        para.paragraph_format.keep_with_next = True
        forms.add_paragraph(f"{number}. {stem}")
        if question["type"] == "multiple_choice":
            for i, option in enumerate(question["options"]):
                line = f"{chr(65+i)}. {option}"
                student.add_paragraph(line)
                forms.add_paragraph(line)
            correct = ", ".join(chr(65 + i) for i in question["correct_option_indices"])
            answer = "Correct options / 正确选项: " + correct
        else:
            answer = question["answer"]
            for _ in range(question["working_lines"]):
                student.add_paragraph(
                    "________________________________________________________________"
                )
        teacher.add_paragraph(f"{number}. {stem}", "Heading 2")
        for label, value in [
            ("Answer / 答案", answer),
            ("Explanation / 解析", question["explanation"]),
            ("Rubric / 评分标准", question["rubric"]),
            ("Objective / 学习目标", question["objective"]),
            ("Difficulty / 层级", question["difficulty"]),
            ("Common error / 常见错误", question["common_error"]),
            (
                "Source / 来源",
                question["source_reference"] or "AI original / AI 原创，教师复核",
            ),
        ]:
            if value:
                teacher.add_paragraph(label + ": " + value)
    result = []
    for kind, document in [
        ("student-exam", student),
        ("teacher-answer-key", teacher),
        ("forms-import", forms),
    ]:
        buffer = BytesIO()
        document.save(buffer)
        content = buffer.getvalue()
        if len(content) >= 10 * 1024**2:
            raise ValueError("Generated Word file exceeds Forms 10 MiB limit")
        result.append((kind, content))
    return result


class Tools:
    async def create_assessment_files(
        self, exam_json: str, __user__: dict = None
    ) -> str:
        """Create three local Word files from a reviewed question bank, not from a filesystem path.

        Use only after reading the teacher's authorized source document and presenting a question draft.
        Schema: title, course, grade(integer 8-12), language, duration_minutes, instructions,
        questions(list of objects with type multiple_choice/open_text, stem, points, objective,
        explanation, difficulty, source_reference, common_error; MC needs options and
        correct_option_indices(zero-based); open_text needs answer, rubric, working_lines).
        Do not include student personal data. No network access or automatic Forms publication.

        :param exam_json: A JSON string matching the documented schema, maximum 40 questions.
        """
        if (
            not __user__
            or not __user__.get("id")
            or __user__.get("role") not in ("admin", "user")
        ):
            return "Denied: an authenticated active user is required."
        try:
            data = validate(exam_json)
        except (ValueError, TypeError, KeyError):
            return "Invalid assessment structure. Check required fields, options, answers and limits."
        from open_webui.storage.provider import Storage, LocalStorageProvider
        from open_webui.models.files import Files, FileForm

        if not isinstance(Storage, LocalStorageProvider):
            return "Stopped: local storage is required; external file storage is not enabled for this tool."
        async with _GATE:
            documents = await asyncio.to_thread(build_documents, data)
            links = []
            labels = {
                "student-exam": "学生试卷 / Student exam",
                "teacher-answer-key": "教师答案与评分 / Teacher key",
                "forms-import": "Forms 导入版 / Forms import",
            }
            for kind, content in documents:
                file_id = str(uuid4())
                filename = "CSEEC-" + kind + "-" + file_id[:8] + ".docx"
                _, path = Storage.upload_file(
                    BytesIO(content), file_id + "_" + filename, {}
                )
                item = await Files.insert_new_file(
                    __user__["id"],
                    FileForm(
                        id=file_id,
                        filename=filename,
                        path=path,
                        hash=hashlib.sha256(content).hexdigest(),
                        data={},
                        meta={
                            "name": filename,
                            "content_type": MIME,
                            "size": len(content),
                            "cseec_kind": kind,
                            "teacher_review_required": True,
                        },
                    ),
                )
                if not item:
                    return "File registration failed. Do not claim that all files were created successfully."
                links.append(f"[{labels[kind]}](/api/v1/files/{file_id}/content)")
        return (
            "\n\n".join(links)
            + "\n\n"
            + (
                "Drafts require teacher review. Word layout is not visually rendered by this tool. "
                "Download the Forms import file, then Microsoft Forms > Quick Import > Upload from this device > Quiz. "
                "Review every question; set correct answers, points, multiple-answer and required settings in Forms. "
                "No online Form has been created or published. Complex equations, diagrams and matching require manual editing."
            )
        )
