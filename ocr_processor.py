"""
OCR Processor for PRD Creator
SEC-002: Configure OCR for text extraction from images
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional
from io import BytesIO

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from config import TESSERACT_PATH, ALLOWED_EXTENSIONS, MAX_IMAGE_SIZE
from exceptions import OCRError

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Handles OCR text extraction from images and PDFs."""

    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialize the OCR processor.

        Args:
            tesseract_path: Path to tesseract executable (uses config default if None)
        """
        if not OCR_AVAILABLE:
            raise OCRError(
                "OCR dependencies not installed. Run: pip install pytesseract Pillow",
                details={"install": "Also install Tesseract from https://github.com/tesseract-ocr/tesseract"}
            )

        self.tesseract_path = tesseract_path or TESSERACT_PATH
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path

        # Validate Tesseract is available
        self._validate_tesseract()

    def _validate_tesseract(self) -> None:
        """Check if Tesseract is available and working."""
        if not os.path.exists(self.tesseract_path):
            raise OCRError(
                f"Tesseract not found at {self.tesseract_path}",
                details={"suggestion": "Install Tesseract or set TESSERACT_PATH in .env"}
            )

        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract version: {version}")
        except Exception as e:
            raise OCRError(
                f"Tesseract validation failed: {e}",
                file_path=self.tesseract_path
            )

    def extract_from_file(self, file_path: str) -> str:
        """
        Extract text from an image or PDF file.

        Args:
            file_path: Path to the file

        Returns:
            Extracted text content

        Raises:
            OCRError: If extraction fails
        """
        path = Path(file_path)

        if not path.exists():
            raise OCRError(f"File not found: {file_path}", file_path=file_path)

        if path.suffix.lower()[1:] not in ALLOWED_EXTENSIONS:
            raise OCRError(
                f"Unsupported file type: {path.suffix}",
                file_path=file_path,
                details={"allowed": list(ALLOWED_EXTENSIONS)}
            )

        if path.suffix.lower() == ".pdf":
            return self._extract_from_pdf(path)
        else:
            return self._extract_from_image(path)

    def extract_from_bytes(self, data: bytes, filename: str) -> str:
        """
        Extract text from uploaded file data.

        Args:
            data: File bytes data
            filename: Original filename (for extension detection)

        Returns:
            Extracted text content
        """
        # Check file size
        if len(data) > MAX_IMAGE_SIZE:
            raise OCRError(
                f"File too large: {len(data) / 1024 / 1024:.1f}MB",
                file_path=filename,
                details={"max_size_mb": MAX_IMAGE_SIZE / 1024 / 1024}
            )

        try:
            image = Image.open(BytesIO(data))

            # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            # Preprocess the image
            image = self._preprocess_image(image)

            # Extract text
            text = pytesseract.image_to_string(
                image,
                lang="eng",
                config="--psm 3 -c preserve_interword_spaces=1"
            )

            return self._clean_text(text)

        except Exception as e:
            raise OCRError(
                f"Failed to extract text: {e}",
                file_path=filename,
                details={"error_type": type(e).__name__}
            )

    def _extract_from_image(self, image_path: Path) -> str:
        """Extract text from an image file."""
        try:
            image = Image.open(image_path)
            image = self._preprocess_image(image)

            text = pytesseract.image_to_string(
                image,
                lang="eng",
                config="--psm 3 -c preserve_interword_spaces=1"
            )

            return self._clean_text(text)

        except Exception as e:
            raise OCRError(
                f"Image processing failed: {e}",
                file_path=str(image_path)
            )

    def _extract_from_pdf(self, pdf_path: Path) -> str:
        """Extract text from a PDF file."""
        try:
            # Try pdf2image first (better quality)
            from pdf2image import convert_from_path

            images = convert_from_path(pdf_path, dpi=200)
            all_text = []

            for i, image in enumerate(images):
                logger.info(f"Processing PDF page {i + 1}/{len(images)}")
                image = self._preprocess_image(image)
                text = pytesseract.image_to_string(image, lang="eng")
                all_text.append(text)

            return self._clean_text("\n\n".join(all_text))

        except ImportError:
            # Fallback to pdfplumber (faster but lower quality)
            try:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages]
                    return self._clean_text("\n\n".join(pages_text))

            except ImportError:
                raise OCRError(
                    "PDF processing requires pdf2image or pdfplumber",
                    file_path=str(pdf_path),
                    details={"install": "pip install pdf2image pdfplumber"}
                )
        except Exception as e:
            raise OCRError(
                f"PDF processing failed: {e}",
                file_path=str(pdf_path)
            )

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image to improve OCR accuracy.

        Steps:
        1. Convert to grayscale
        2. Resize if too small
        3. Enhance contrast
        4. Apply slight sharpening
        5. Remove noise
        """
        # Convert to grayscale
        if image.mode != "L":
            image = image.convert("L")

        # Resize if too small (improves accuracy)
        width, height = image.size
        if width < 1000 or height < 1000:
            scale = max(1000 / width, 1000 / height)
            new_size = (int(width * scale), int(height * scale))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)

        # Sharpen
        image = image.filter(ImageFilter.SHARPEN)

        # Remove noise (median filter)
        image = image.filter(ImageFilter.MedianFilter(size=3))

        return image

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text by removing artifacts.

        - Remove excessive whitespace
        - Fix common OCR errors
        - Remove special characters that are likely noise
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove common OCR artifacts
        text = re.sub(r"[|]{5,}", "", text)  # Lines of pipe characters
        text = re.sub(r"[=_]{10,}", "", text)  # Lines of equals/underscores

        # Fix broken words (common in columns)
        text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)

        # Strip and return
        return text.strip()


# Singleton instance for reuse
_processor: Optional[OCRProcessor] = None


def get_ocr_processor() -> OCRProcessor:
    """Get or create the OCR processor singleton."""
    global _processor
    if _processor is None:
        _processor = OCRProcessor()
    return _processor
