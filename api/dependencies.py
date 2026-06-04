# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
FastAPI Dependencies

Provides dependency injection for XinzhiVideoAICore and other services.
"""

from typing import Annotated
from fastapi import Depends
from loguru import logger

from xinzhi_video_ai.service import XinzhiVideoAICore


# Global Xinzhi Video AI instance
_xinzhi_video_ai_instance: XinzhiVideoAICore = None


async def get_xinzhi_video_ai() -> XinzhiVideoAICore:
    """
    Get Xinzhi Video AI core instance (dependency injection)
    
    Returns:
        XinzhiVideoAICore instance
    """
    global _xinzhi_video_ai_instance
    
    if _xinzhi_video_ai_instance is None:
        _xinzhi_video_ai_instance = XinzhiVideoAICore()
        await _xinzhi_video_ai_instance.initialize()
        logger.info("✅ Xinzhi Video AI initialized for API")
    
    return _xinzhi_video_ai_instance


async def shutdown_xinzhi_video_ai():
    """Shutdown Xinzhi Video AI instance and cleanup resources"""
    global _xinzhi_video_ai_instance
    if _xinzhi_video_ai_instance:
        logger.info("Shutting down Xinzhi Video AI...")
        await _xinzhi_video_ai_instance.cleanup()
        _xinzhi_video_ai_instance = None
    
    from xinzhi_video_ai.services.frame_html import HTMLFrameGenerator
    await HTMLFrameGenerator.close_browser()


# Type alias for dependency injection
XinzhiVideoAIDep = Annotated[XinzhiVideoAICore, Depends(get_xinzhi_video_ai)]
