"""Functionality for splitting text."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional, cast

from core.model_manager import ModelInstance
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.model_runtime.model_providers.__base.tokenizers.gpt2_tokenzier import GPT2Tokenizer
from core.splitter.text_splitter import (
    TS,
    Collection,
    Literal,
    RecursiveCharacterTextSplitter,
    Set,
    TokenTextSplitter,
    Union,
)

logger = logging.getLogger(__name__)


class EnhanceRecursiveCharacterTextSplitter(RecursiveCharacterTextSplitter):
    """
        This class is used to implement from_gpt2_encoder, to prevent using of tiktoken
    """

    @classmethod
    def from_encoder(
            cls: type[TS],
            embedding_model_instance: Optional[ModelInstance],
            allowed_special: Union[Literal[all], Set[str]] = set(),
            disallowed_special: Union[Literal[all], Collection[str]] = "all",
            **kwargs: Any,
    ):
        def _token_encoder(text: str) -> int:
            if not text:
                return 0

            if embedding_model_instance:
                embedding_model_type_instance = embedding_model_instance.model_type_instance
                embedding_model_type_instance = cast(TextEmbeddingModel, embedding_model_type_instance)
                return embedding_model_type_instance.get_num_tokens(
                    model=embedding_model_instance.model,
                    credentials=embedding_model_instance.credentials,
                    texts=[text]
                )
            else:
                return GPT2Tokenizer.get_num_tokens(text)

        if issubclass(cls, TokenTextSplitter):
            extra_kwargs = {
                "model_name": embedding_model_instance.model if embedding_model_instance else 'gpt2',
                "allowed_special": allowed_special,
                "disallowed_special": disallowed_special,
            }
            kwargs = {**kwargs, **extra_kwargs}

        return cls(length_function=_token_encoder, **kwargs)


class FixedRecursiveCharacterTextSplitter(EnhanceRecursiveCharacterTextSplitter):
    def __init__(self, fixed_separator: str = "\n\n", separators: Optional[list[str]] = None, **kwargs: Any):
        """Create a new TextSplitter."""
        super().__init__(**kwargs)
        self._fixed_separator = fixed_separator
        self._separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> list[str]:
        """Split incoming text and return chunks."""
        if self._fixed_separator:
            chunks = text.split(self._fixed_separator)
        else:
            chunks = list(text)

        final_chunks = []
        for chunk in chunks:
            if self._length_function(chunk) > self._chunk_size:
                final_chunks.extend(self.recursive_split_text(chunk))
            else:
                final_chunks.append(chunk)

        return final_chunks

    def recursive_split_text(self, text: str) -> list[str]:
        """Split incoming text and return chunks."""
        final_chunks = []
        # Get appropriate separator to use
        separator = self._separators[-1]
        for _s in self._separators:
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                break
        # Now that we have the separator, split the text
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)
        # Now go merging things, recursively splitting longer texts.
        _good_splits = []
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, separator)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                other_info = self.recursive_split_text(s)
                final_chunks.extend(other_info)
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, separator)
            final_chunks.extend(merged_text)
        return final_chunks


# TODO(chiyu): fix all corner cases
class CustomRecursiveCharacterTextSplitter(FixedRecursiveCharacterTextSplitter):
    def split_text(self, text: str) -> list[str]:
        split_texts = extract_sections(text)
        outputs = []
        for chapter_info, section_text in split_texts:
            outputs.append(f"{chapter_info}\n{section_text}")
        return outputs


def extract_sections(text: str):
    '''
        正则表达式拆分章节和附件
        TODO(liutong): 附件处理, 当前没有添加附件到数据库中
    '''
    # 解析章节
    attachment_pattern = re.compile(r'-\s*\d+\s*-\s*附件(?:\d+\s*)?\s*((?:.|\n)*?)(?=-\s*\d+\s*-|附件\d+|$)', re.DOTALL)
    attachment_matches = attachment_pattern.finditer(text)

    attachment_contents = []
    for i, match in enumerate(attachment_matches):
        if i == 0:
            chapter_content = text[:match.start()].strip()
        attachment_contents.append(text[match.start():match.end()])

    if len(attachment_contents) == 0:
        chapter_content = text

    # 删掉页码信息
    chapter_content = re.sub(r'-\s*\d+\s*-', '', chapter_content).strip()

    # 匹配章节信息
    chapter_pattern = re.compile(r'第(\S+)章\s*(\S+?)\s*([\s\S]*?)(?=第\S+章\s*\S+?\s*|\Z)', re.DOTALL)
    chapter_matches = chapter_pattern.findall(chapter_content)

    if chapter_matches == [] and chapter_content != '':
        # 没有章节只有条目： 处理条目 
        section_pattern = re.compile(r'第(\S+)条\s*(.+?)(?=第\S+条\s*|\Z)', re.DOTALL)
        section_matches = section_pattern.findall(chapter_content)
        sections = []
        for section_match in section_matches:
            section_num, section_content = section_match
            sections.append((f"第{section_num}条", section_content)) # section info, section content
    else:
        sections = []
        for match in chapter_matches:
            chapter_num, chapter_title, section_info = match
            end_token = section_info.find("\r\n")
            if end_token != -1:
                chapter_title += section_info[:end_token]
            else:
                end_token = section_info.find("\n")
                if end_token != -1:
                    chapter_title += section_info[:end_token]
            chapter_info = f"第{chapter_num}章 {chapter_title}"
            section_matches = re.findall(r'第(\S+)条\s*(.+?)(?=第\S+条\s*|\Z)', section_info, re.DOTALL)
            for section_match in section_matches:
                section_num, section_content = section_match
                section = f"第{section_num}条 {section_content.strip()}"
                sections.append((chapter_info, section))

    return sections