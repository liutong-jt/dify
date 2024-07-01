"""Abstract interface for document loader implementations."""
import base64
from typing import Optional
import logging

import cv2
import numpy as np
from paddleocr import PaddleOCR

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document
from extensions.ext_storage import storage


logging.basicConfig(format='%(asctime)s %(pathname)s line:%(lineno)d [%(levelname)s] %(message)s', level='INFO')


class UnstructuredImageExtractor(BaseExtractor):
    """Load text files.


    Args:
        file_path: Path to the file to load.
    """

    def __init__(
            self,
            file_path: str,
            file_cache_key: Optional[str] = None
    ):
        """Initialize with file path."""
        self._file_path = file_path
        self._file_cache_key = file_cache_key

    def extract(self) -> list[Document]:
        """Load from file path."""
        plaintext_file_key = ''
        plaintext_file_exists = False
        if self._file_cache_key:
            try:
                text = storage.load(self._file_cache_key).decode('utf-8')
                plaintext_file_exists = True
                return [Document(page_content=text)]
            except FileNotFoundError:
                pass
            
        img_np = cv2.imread(self._file_path)
        h,w,c = img_np.shape
        img_data = {"img64": base64.b64encode(img_np).decode("utf-8"), "height": h, "width": w, "channels": c}
        result = self._ocr(img_data)
        result = [line for line in result if line]
        ocr_result = [i[1][0] for line in result for i in line]
        text = "\n".join(ocr_result)
        
        
        metadata = {"source": self._file_path}
        text = text.encode('utf-8')
        # save plaintext file for caching
        if not plaintext_file_exists and plaintext_file_key:
            storage.save(plaintext_file_key, text.encode('utf-8'))
            
        return [Document(page_content=text, metadata=metadata)]


    def _ocr(self, img_data):
        ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", use_gpu=True, show_log=False)

        img_file = img_data['img64']
        height = img_data['height']
        width = img_data['width']
        channels = img_data['channels']

        binary_data = base64.b64decode(img_file)
        img_array = np.frombuffer(binary_data, dtype=np.uint8).reshape((height, width, channels))

        if not img_file:
            return 'error: No file was uploaded.'

        result = ocr_engine.ocr(img_array)
        return result