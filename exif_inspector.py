import io
from datetime import datetime
from PIL import Image, ExifTags


def extract_and_verify_exif(
    image_bytes: bytes,
    deadline_str: str | None = None,
) -> dict:
    """
    Extracts EXIF metadata from an image and verifies if the photo creation date
    aligns with the milestone timeline.

    Args:
        image_bytes: Raw bytes of the uploaded image file.
        deadline_str: Optional milestone deadline string (e.g., 'YYYY-MM-DD').

    Returns:
        dict containing EXIF tags, creation date, timeline alignment flag, and feedback.
    """
    result = {
        "has_exif": False,
        "photo_date": None,
        "is_aligned": True,
        "camera_make": None,
        "camera_model": None,
        "software": None,
        "timeline_feedback": "No EXIF metadata found (metadata may have been stripped or image is a digital export/screenshot).",
        "raw_tags": {},
    }

    try:
        image = Image.open(io.BytesIO(image_bytes))
        exif_raw = image.getexif()

        if not exif_raw:
            return result

        result["has_exif"] = True
        named_tags = {}

        for tag_id, val in exif_raw.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            named_tags[tag_name] = str(val)

        # Also inspect IFD EXIF data if present
        exif_ifd = exif_raw.get_ifd(ExifTags.IFD.Exif)
        for tag_id, val in exif_ifd.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            named_tags[tag_name] = str(val)

        result["raw_tags"] = named_tags
        result["camera_make"] = named_tags.get("Make")
        result["camera_model"] = named_tags.get("Model")
        result["software"] = named_tags.get("Software")

        # Extract photo creation timestamp
        date_str = (
            named_tags.get("DateTimeOriginal")
            or named_tags.get("DateTimeDigitized")
            or named_tags.get("DateTime")
        )

        if not date_str:
            result["timeline_feedback"] = "EXIF data present, but no photo creation date tag (DateTimeOriginal) found."
            return result

        result["photo_date"] = date_str

        # Parse EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
        parsed_photo_date = None
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed_photo_date = datetime.strptime(date_str.strip(), fmt)
                break
            except ValueError:
                continue

        if not parsed_photo_date:
            result["timeline_feedback"] = f"Photo creation date tag found ({date_str}), but could not be parsed."
            return result

        # Verify alignment with milestone deadline
        if deadline_str and deadline_str.strip() and deadline_str.strip().lower() != "open":
            parsed_deadline = None
            for dfmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    parsed_deadline = datetime.strptime(deadline_str.strip(), dfmt)
                    break
                except ValueError:
                    continue

            if parsed_deadline:
                # Add 24-hour grace period for end-of-day deadline
                deadline_end_of_day = parsed_deadline.replace(hour=23, minute=59, second=59)

                if parsed_photo_date > deadline_end_of_day:
                    diff_days = (parsed_photo_date - deadline_end_of_day).days + 1
                    result["is_aligned"] = False
                    result["timeline_feedback"] = (
                        f"TIMELINE ANOMALY: Photo was captured on {parsed_photo_date.strftime('%Y-%m-%d %H:%M')}, "
                        f"which is {diff_days} day(s) AFTER the milestone deadline ({deadline_str})."
                    )
                else:
                    result["is_aligned"] = True
                    result["timeline_feedback"] = (
                        f"TIMELINE VERIFIED: Photo captured on {parsed_photo_date.strftime('%Y-%m-%d %H:%M')}, "
                        f"within the milestone deadline ({deadline_str})."
                    )
            else:
                result["timeline_feedback"] = f"Photo captured on {parsed_photo_date.strftime('%Y-%m-%d %H:%M')}."
        else:
            result["timeline_feedback"] = f"Photo captured on {parsed_photo_date.strftime('%Y-%m-%d %H:%M')}."

    except Exception as e:
        result["timeline_feedback"] = f"EXIF parsing notice: {str(e)}"

    return result

