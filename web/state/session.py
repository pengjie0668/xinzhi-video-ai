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
Session state management for web UI
"""

import streamlit as st
from loguru import logger

from web.i18n import get_language, set_language
from web.utils.async_helpers import run_async


def init_session_state():
    """Initialize session state variables"""
    if "language" not in st.session_state:
        # Use auto-detected system language
        st.session_state.language = get_language()


def init_i18n():
    """Initialize internationalization"""
    # Locales are already loaded and system language detected on import
    # Get language from session state or use auto-detected system language
    if "language" not in st.session_state:
        st.session_state.language = get_language()  # Use auto-detected language
    
    # Set current language
    set_language(st.session_state.language)


def get_xinzhi_video_ai():
    """
    Get initialized Xinzhi Video AI instance with proper caching and cleanup
    
    Uses st.session_state to cache the instance per user session.
    ComfyKit is lazily initialized and automatically recreated on config changes.
    """
    from xinzhi_video_ai.service import XinzhiVideoAICore
    from xinzhi_video_ai.config import config_manager
    
    # Compute config hash for change detection
    import hashlib
    import json
    config_dict = config_manager.config.to_dict()
    # Only track ComfyUI config for hash (other config changes don't need core recreation)
    comfyui_config = config_dict.get("comfyui", {})
    config_hash = hashlib.md5(json.dumps(comfyui_config, sort_keys=True).encode()).hexdigest()
    
    # Check if we need to create or recreate core instance
    need_recreate = False
    if 'xinzhi_video_ai' not in st.session_state:
        need_recreate = True
        logger.info("Creating new XinzhiVideoAICore instance (first time)")
    elif st.session_state.get('xinzhi_video_ai_config_hash') != config_hash:
        need_recreate = True
        logger.info("Configuration changed, recreating XinzhiVideoAICore instance")
        # Cleanup old instance
        old_core = st.session_state.xinzhi_video_ai
        try:
            run_async(old_core.cleanup())
        except Exception as e:
            logger.warning(f"Failed to cleanup old XinzhiVideoAICore: {e}")
    
    if need_recreate:
        # Create and initialize new instance
        xinzhi_video_ai = XinzhiVideoAICore()
        run_async(xinzhi_video_ai.initialize())
        
        # Cache in session state
        st.session_state.xinzhi_video_ai = xinzhi_video_ai
        st.session_state.xinzhi_video_ai_config_hash = config_hash
        logger.info("✅ XinzhiVideoAICore initialized and cached")
    else:
        xinzhi_video_ai = st.session_state.xinzhi_video_ai
        logger.debug("Reusing cached XinzhiVideoAICore instance")
    
    return xinzhi_video_ai

