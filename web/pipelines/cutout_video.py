# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0

"""Product cutout to video pipeline UI."""

import os
import tempfile
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import requests
import streamlit as st
from loguru import logger
from PIL import Image, ImageFilter, ImageOps

from xinzhi_video_ai.config import config_manager
from xinzhi_video_ai.models.progress import ProgressEvent
from xinzhi_video_ai.pipelines.asset_based import AssetBasedPipeline
from web.components.content_input import render_bgm_section, render_version_info
from web.i18n import get_language, tr
from web.pipelines.api_workflows import (
    is_api_workflow,
    list_api_media_workflows,
    render_api_video_controls,
)
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.utils.async_helpers import run_async


def _list_cutout_video_workflows(xinzhi_video_ai: Any) -> list[dict]:
    """List API and Comfy video workflows that can be selected by this tab."""
    workflows: list[dict] = []
    seen: set[str] = set()

    for workflow in list_api_media_workflows(
        xinzhi_video_ai,
        "video",
        required_adapter_abilities=["first_frame_i2v"],
        verified_only=True,
    ):
        key = workflow.get("key")
        if key and key not in seen:
            workflows.append({**workflow, "service": "api"})
            seen.add(key)

    media_service = getattr(xinzhi_video_ai, "media", None)
    if media_service is None:
        return workflows

    try:
        for workflow in media_service.list_workflows():
            key = workflow.get("key", "")
            source = workflow.get("source", "")
            name = workflow.get("name", "")
            if not key or key in seen or key.startswith("api/"):
                continue
            if source not in {"runninghub", "selfhost"}:
                continue
            if not name.startswith(("i2v_", "video_")):
                continue
            if any(marker in name.lower() for marker in ("understanding", "analysis", "analyse")):
                continue

            workflow_kind = "i2v" if name.startswith("i2v_") else "video"
            workflows.append({**workflow, "service": source, "workflow_kind": workflow_kind})
            seen.add(key)
    except Exception as exc:
        logger.warning(f"Failed to list Comfy video workflows: {exc}")

    service_order = {"runninghub": 0, "selfhost": 1, "api": 2}
    kind_order = {"i2v": 0, "video": 1}
    return sorted(
        workflows,
        key=lambda wf: (
            service_order.get(wf.get("service"), 9),
            kind_order.get(wf.get("workflow_kind"), 9),
            wf.get("display_name") or wf.get("key", ""),
        ),
    )


class CutoutVideoPipelineUI(PipelineUI):
    """Upload one image, remove the background, then generate a video from it."""

    name = "cutout_video"
    icon = "✂️"

    @property
    def display_name(self):
        return "抠图视频" if get_language() == "zh_CN" else "Cutout Video"

    @property
    def description(self):
        return (
            "上传单张图片，先抠出透明主体，再基于主体生成视频。"
            if get_language() == "zh_CN"
            else "Upload one image, cut out the subject, then generate a video."
        )

    def render(self, xinzhi_video_ai: Any):
        left_col, middle_col, right_col = st.columns([1, 1, 1])

        with left_col:
            cutout_params = self._render_cutout_input()
            bgm_params = render_bgm_section(key_prefix="cutout_")
            render_version_info()

        with middle_col:
            config_params = self._render_generation_config(xinzhi_video_ai)

        with right_col:
            video_params = {
                **cutout_params,
                **bgm_params,
                **config_params,
            }
            self._render_output_preview(xinzhi_video_ai, video_params)

    def _render_cutout_input(self) -> dict:
        zh = get_language() == "zh_CN"
        with st.container(border=True):
            st.markdown("**✂️ 商品抠图**" if zh else "**✂️ Product Cutout**")

            cutout_method = st.radio(
                "抠图方式" if zh else "Cutout method",
                ["aliyun", "local"],
                format_func=lambda value: {
                    "aliyun": "阿里云商品分割 API" if zh else "Aliyun commodity segmentation API",
                    "local": "本地白底抠图（备用）" if zh else "Local white-background cutout",
                }[value],
                index=0,
                horizontal=True,
                key="cutout_method",
            )

            aliyun_access_key_id = ""
            aliyun_access_key_secret = ""
            if cutout_method == "aliyun":
                env_access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID") or os.getenv("ALIYUN_ACCESS_KEY_ID") or ""
                env_access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or os.getenv("ALIYUN_ACCESS_KEY_SECRET") or ""

                if env_access_key_id and env_access_key_secret:
                    st.caption(
                        "已从服务器环境变量读取阿里云 AccessKey。"
                        if zh
                        else "Aliyun AccessKey loaded from server environment variables."
                    )
                    aliyun_access_key_id = env_access_key_id
                    aliyun_access_key_secret = env_access_key_secret
                else:
                    aliyun_access_key_id = st.text_input(
                        "阿里云 AccessKey ID" if zh else "Aliyun AccessKey ID",
                        type="password",
                        key="cutout_aliyun_access_key_id",
                    )
                    aliyun_access_key_secret = st.text_input(
                        "阿里云 AccessKey Secret" if zh else "Aliyun AccessKey Secret",
                        type="password",
                        key="cutout_aliyun_access_key_secret",
                    )
                    st.caption(
                        "这里用的是阿里云视觉智能开放平台 Imageseg 的 AccessKey，不是 DashScope API Key。"
                        if zh
                        else "This uses Aliyun Imageseg AccessKey, not a DashScope API key."
                    )

            uploaded_file = st.file_uploader(
                "上传商品图片" if zh else "Upload product image",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=False,
                help=(
                    "当前使用本地浅色/白底抠图，适合商品白底图；复杂背景后续可接入专业抠图 API。"
                    if zh
                    else "Uses local light/white-background cutout. A professional matting API can be added later."
                ),
                key="cutout_source_image",
            )

            tolerance = 36
            feather = 1
            if cutout_method == "local":
                tolerance = st.slider(
                    "背景容差" if zh else "Background tolerance",
                    min_value=8,
                    max_value=90,
                    value=36,
                    step=2,
                    help=(
                        "背景没抠干净就调高；主体被误删就调低。"
                        if zh
                        else "Increase if background remains; decrease if the subject is removed."
                    ),
                    key="cutout_tolerance",
                )
                feather = st.slider(
                    "边缘柔化" if zh else "Edge feather",
                    min_value=0,
                    max_value=4,
                    value=1,
                    step=1,
                    key="cutout_feather",
                )

            source_path = None
            cutout_path = None
            if uploaded_file:
                session_id = st.session_state.get("cutout_session_id")
                if not session_id:
                    session_id = uuid.uuid4().hex[:12]
                    st.session_state["cutout_session_id"] = session_id

                temp_dir = Path(f"temp/cutout_{session_id}")
                temp_dir.mkdir(parents=True, exist_ok=True)

                safe_name = Path(uploaded_file.name).name
                source_path = temp_dir / safe_name
                source_path.write_bytes(uploaded_file.getbuffer())
                cutout_path = temp_dir / f"{Path(safe_name).stem}_cutout.png"

                try:
                    if cutout_method == "aliyun":
                        if not aliyun_access_key_id or not aliyun_access_key_secret:
                            raise ValueError(
                                "请填写阿里云 AccessKey ID 和 AccessKey Secret。"
                                if zh
                                else "Enter Aliyun AccessKey ID and AccessKey Secret."
                            )
                        self._create_aliyun_cutout(
                            source_path,
                            cutout_path,
                            access_key_id=aliyun_access_key_id,
                            access_key_secret=aliyun_access_key_secret,
                        )
                    else:
                        self._create_cutout(source_path, cutout_path, tolerance=tolerance, feather=feather)

                    st.success("抠图完成" if zh else "Cutout ready")

                    preview_cols = st.columns(2)
                    with preview_cols[0]:
                        st.caption("原图" if zh else "Original")
                        st.image(str(source_path), use_container_width=True)
                    with preview_cols[1]:
                        st.caption("透明 PNG" if zh else "Transparent PNG")
                        st.image(str(cutout_path), use_container_width=True)

                    with open(cutout_path, "rb") as f:
                        st.download_button(
                            "下载透明 PNG" if zh else "Download PNG",
                            data=f.read(),
                            file_name=cutout_path.name,
                            mime="image/png",
                            use_container_width=True,
                            key="cutout_download_png",
                        )
                except Exception as exc:
                    st.error(f"抠图失败：{exc}" if zh else f"Cutout failed: {exc}")
                    logger.exception(exc)
                    cutout_path = None
            else:
                st.info("先上传一张商品图。" if zh else "Upload one product image first.")

        return {
            "source_image": str(source_path.absolute()) if source_path else None,
            "cutout_image": str(cutout_path.absolute()) if cutout_path else None,
        }

    def _render_generation_config(self, xinzhi_video_ai: Any) -> dict:
        zh = get_language() == "zh_CN"

        with st.container(border=True):
            st.markdown("**🎬 视频设置**" if zh else "**🎬 Video Settings**")

            video_title = st.text_input(
                "视频标题" if zh else "Video title",
                placeholder="例如：618 商品种草短视频" if zh else "e.g. Summer product promo",
                key="cutout_video_title",
            )
            intent = st.text_area(
                "生成要求/口播方向" if zh else "Prompt / narration direction",
                placeholder=(
                    "例如：突出产品高级感、白底干净、镜头慢推、适合电商详情页。"
                    if zh
                    else "e.g. Premium product promo with clean white background and slow camera push."
                ),
                height=110,
                key="cutout_intent",
            )
            duration = st.slider(
                "目标时长（秒）" if zh else "Target duration (seconds)",
                min_value=5,
                max_value=60,
                value=15,
                step=5,
                key="cutout_duration",
            )

        with st.container(border=True):
            st.markdown("**⚙️ 服务配置**" if zh else "**⚙️ Services**")

            api_provider_config = config_manager.config.to_dict().get("api_providers", {})
            has_api_analysis = any(
                bool((api_provider_config.get(provider, {}) or {}).get("api_key"))
                for provider in ("dashscope", "openai", "gemini")
            )
            has_runninghub = bool(config_manager.get_comfyui_config().get("runninghub_api_key"))

            source_options = ["api", "runninghub", "selfhost"]
            default_source = "api" if has_api_analysis else ("runninghub" if has_runninghub else "selfhost")
            source = st.radio(
                "素材分析方式" if zh else "Asset analysis",
                source_options,
                format_func=lambda key: {
                    "api": "API VLM 素材分析" if zh else "API VLM",
                    "runninghub": "RunningHub 云端" if zh else "RunningHub",
                    "selfhost": "SelfHost 本地" if zh else "SelfHost",
                }[key],
                index=source_options.index(default_source),
                horizontal=True,
                key="cutout_analysis_source",
            )

            video_workflows = _list_cutout_video_workflows(xinzhi_video_ai)
            available_services = []
            for workflow in video_workflows:
                service = workflow.get("service")
                if service and service not in available_services:
                    available_services.append(service)

            preferred_service = "runninghub" if has_runninghub else ("api" if has_api_analysis else "selfhost")
            if preferred_service not in available_services and available_services:
                preferred_service = available_services[0]

            api_video_workflow = None
            api_video_params = {}
            if available_services:
                video_service = st.radio(
                    "图生视频服务" if zh else "Image-to-video service",
                    available_services,
                    format_func=lambda key: {
                        "api": "API 服务（DashScope/Ark/Kling）" if zh else "API provider",
                        "runninghub": "RunningHub 云端" if zh else "RunningHub cloud",
                        "selfhost": "SelfHost 本地" if zh else "SelfHost local",
                    }.get(key, key),
                    index=available_services.index(preferred_service),
                    horizontal=True,
                    key="cutout_video_service",
                )

                selected_workflows = [wf for wf in video_workflows if wf.get("service") == video_service]
                workflow_options = [wf["display_name"] for wf in selected_workflows]

                selected_display = st.selectbox(
                    "图生视频模型/工作流" if zh else "Image-to-video model/workflow",
                    workflow_options,
                    index=0,
                    key="cutout_video_workflow",
                )
                selected_index = workflow_options.index(selected_display)
                selected_workflow = selected_workflows[selected_index]
                api_video_workflow = selected_workflow["key"]

                if is_api_workflow(api_video_workflow):
                    api_video_params = render_api_video_controls(
                        selected_workflow,
                        key_prefix="cutout",
                        default_duration=duration,
                        allow_audio_driven=True,
                        show_duration=True,
                        default_ratio="9:16",
                    )
                else:
                    with st.expander("RunningHub/SelfHost 视频参数" if zh else "RunningHub/SelfHost video options", expanded=False):
                        st.caption(
                            "会把抠图后的透明 PNG 作为 image_path 传入工作流；请选择支持首帧图生视频的工作流。"
                            if zh
                            else "The transparent PNG is passed as image/image_path; choose an i2v workflow that supports first-frame image-to-video."
                        )
                        negative_prompt = st.text_area(
                            "负向提示词（可选）" if zh else "Negative prompt (optional)",
                            value="",
                            height=70,
                            key="cutout_comfy_negative_prompt",
                        )
                        if negative_prompt.strip():
                            api_video_params["negative_prompt"] = negative_prompt.strip()

                    if video_service == "runninghub" and not has_runninghub:
                        st.warning(
                            "当前未检测到 RunningHub API Key，选择 RunningHub 工作流会生成失败。"
                            if zh
                            else "RunningHub API Key is not configured; RunningHub workflows will fail."
                        )
            else:
                st.warning(
                    "没有可用的图生视频模型/工作流，请先配置 API Key 或 RunningHub/SelfHost 工作流。"
                    if zh
                    else "No image-to-video model/workflow is available. Configure an API key or RunningHub/SelfHost workflow first."
                )

        with st.container(border=True):
            st.markdown(f"**{tr('section.tts')}**")
            from xinzhi_video_ai.tts_voices import EDGE_TTS_VOICES, get_voice_display_name

            voice_options = []
            voice_ids = []
            default_voice_index = 0
            saved_voice = (
                config_manager.get_comfyui_config()
                .get("tts", {})
                .get("local", {})
                .get("voice", "zh-CN-YunjianNeural")
            )
            for idx, voice_config in enumerate(EDGE_TTS_VOICES):
                voice_id = voice_config["id"]
                voice_options.append(get_voice_display_name(voice_id, tr, get_language()))
                voice_ids.append(voice_id)
                if voice_id == saved_voice:
                    default_voice_index = idx

            selected_voice = st.selectbox(
                tr("tts.voice_selector"),
                voice_options,
                index=default_voice_index,
                key="cutout_tts_voice",
            )
            tts_speed = st.slider(
                tr("tts.speed"),
                min_value=0.5,
                max_value=2.0,
                value=1.2,
                step=0.1,
                format="%.1fx",
                key="cutout_tts_speed",
            )

        return {
            "video_title": video_title,
            "intent": intent if intent.strip() else None,
            "duration": duration,
            "source": source,
            "api_video_workflow": api_video_workflow,
            "api_video_params": api_video_params,
            "voice_id": voice_ids[voice_options.index(selected_voice)],
            "tts_speed": tts_speed,
        }

    def _render_output_preview(self, xinzhi_video_ai: Any, video_params: dict):
        zh = get_language() == "zh_CN"
        with st.container(border=True):
            st.markdown(f"**{tr('section.video_generation')}**")

            if not config_manager.validate():
                st.warning(tr("settings.not_configured"))

            cutout_image = video_params.get("cutout_image")
            if not cutout_image:
                st.info("完成抠图后即可开始生成视频。" if zh else "Generate video after the cutout is ready.")
                st.button(tr("btn.generate"), type="primary", use_container_width=True, disabled=True, key="cutout_generate_disabled")
                return

            if not video_params.get("api_video_workflow"):
                st.warning("请先选择图生视频模型/工作流。" if zh else "Choose an image-to-video model/workflow first.")
                st.button(tr("btn.generate"), type="primary", use_container_width=True, disabled=True, key="cutout_generate_no_model")
                return

            st.info("已准备好透明主体图，可以开始生成视频。" if zh else "Transparent subject image is ready.")

            if st.button(tr("btn.generate"), type="primary", use_container_width=True, key="cutout_generate"):
                if not config_manager.validate():
                    st.error(tr("settings.not_configured"))
                    st.stop()

                progress_bar = st.progress(0)
                status_text = st.empty()
                start_time = time.time()

                def update_progress(event: ProgressEvent):
                    message = event.event_type
                    if event.event_type == "analyzing_asset":
                        message = (
                            f"分析抠图素材 {event.frame_current}/{event.frame_total}"
                            if zh
                            else f"Analyzing cutout asset {event.frame_current}/{event.frame_total}"
                        )
                    elif event.event_type == "generating_script":
                        message = "生成口播脚本..." if zh else "Generating script..."
                    elif event.event_type == "frame_step":
                        message = (
                            f"处理视频片段 {event.frame_current}/{event.frame_total}"
                            if zh
                            else f"Processing scene {event.frame_current}/{event.frame_total}"
                        )
                    elif event.event_type == "concatenating":
                        message = "合成最终视频..." if zh else "Compositing final video..."
                    elif event.event_type == "completed":
                        message = tr("progress.completed")

                    status_text.text(message)
                    progress_bar.progress(min(int(event.progress * 100), 99))

                try:
                    pipeline = AssetBasedPipeline(xinzhi_video_ai)
                    ctx = run_async(pipeline(
                        assets=[cutout_image],
                        video_title=video_params.get("video_title", ""),
                        intent=video_params.get("intent") or video_params.get("video_title") or (
                            "基于透明主体图生成一个干净、有高级感的电商短视频。"
                            if zh
                            else "Generate a clean premium ecommerce video from the transparent subject image."
                        ),
                        duration=video_params.get("duration", 15),
                        source=video_params.get("source", "api"),
                        bgm_path=video_params.get("bgm_path"),
                        bgm_volume=video_params.get("bgm_volume", 0.2),
                        bgm_mode=video_params.get("bgm_mode", "loop"),
                        api_video_workflow=video_params.get("api_video_workflow"),
                        api_video_params=video_params.get("api_video_params"),
                        voice_id=video_params.get("voice_id", "zh-CN-YunjianNeural"),
                        tts_speed=video_params.get("tts_speed", 1.2),
                        progress_callback=update_progress,
                    ))

                    total_time = time.time() - start_time
                    progress_bar.progress(100)
                    status_text.text(tr("status.success"))

                    if os.path.exists(ctx.final_video_path):
                        st.success(tr("status.video_generated", path=ctx.final_video_path))
                        st.caption(f"⏱️ {total_time:.1f}s")
                        st.video(ctx.final_video_path)
                        with open(ctx.final_video_path, "rb") as video_file:
                            st.download_button(
                                label="⬇️ 下载视频" if zh else "⬇️ Download Video",
                                data=video_file.read(),
                                file_name=os.path.basename(ctx.final_video_path),
                                mime="video/mp4",
                                use_container_width=True,
                            )
                    else:
                        st.error(tr("status.video_not_found", path=ctx.final_video_path))

                except Exception as exc:
                    status_text.text("")
                    progress_bar.empty()
                    st.error(tr("status.error", error=str(exc)))
                    logger.exception(exc)
                    st.stop()

    @staticmethod
    def _create_aliyun_cutout(
        source_path: Path,
        output_path: Path,
        access_key_id: str,
        access_key_secret: str,
    ):
        """Use Aliyun SegmentCommodity mask, then apply it to the original image size."""
        from alibabacloud_imageseg20191230.client import Client
        from alibabacloud_imageseg20191230 import models as imageseg_models
        from alibabacloud_tea_openapi import models as open_api_models
        from alibabacloud_tea_util import models as util_models

        original = Image.open(source_path).convert("RGBA")
        api_image = original.convert("RGB")
        if max(api_image.size) > 2000:
            api_image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            api_input_path = Path(tmp_file.name)

        try:
            api_image.save(api_input_path, "JPEG", quality=95, subsampling=0)

            client = Client(open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                endpoint="imageseg.cn-shanghai.aliyuncs.com",
                region_id="cn-shanghai",
            ))

            with open(api_input_path, "rb") as image_file:
                request = imageseg_models.SegmentCommodityAdvanceRequest(
                    image_urlobject=image_file,
                    return_form="mask",
                )
                response = client.segment_commodity_advance(
                    request,
                    util_models.RuntimeOptions(),
                )

            result_url = response.body.data.image_url if response and response.body and response.body.data else None
            if not result_url:
                raise RuntimeError("Aliyun SegmentCommodity did not return a mask URL.")

            mask_resp = requests.get(result_url, timeout=60)
            mask_resp.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as mask_file:
                mask_path = Path(mask_file.name)
                mask_file.write(mask_resp.content)

            try:
                mask = Image.open(mask_path).convert("L")
                mask = ImageOps.autocontrast(mask)
                if mask.size != original.size:
                    mask = mask.resize(original.size, Image.Resampling.LANCZOS)
                mask = mask.filter(ImageFilter.GaussianBlur(radius=0.6))

                original.putalpha(mask)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                original.save(output_path, "PNG")
            finally:
                if mask_path.exists():
                    mask_path.unlink()
        finally:
            if api_input_path.exists():
                api_input_path.unlink()

    @staticmethod
    def _create_cutout(source_path: Path, output_path: Path, tolerance: int, feather: int):
        image = Image.open(source_path).convert("RGBA")
        max_side = 1800
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        arr = np.array(image)
        rgb = arr[:, :, :3].astype(np.int16)
        height, width = rgb.shape[:2]

        sample = max(4, min(width, height) // 40)
        corner_pixels = np.concatenate([
            rgb[:sample, :sample].reshape(-1, 3),
            rgb[:sample, -sample:].reshape(-1, 3),
            rgb[-sample:, :sample].reshape(-1, 3),
            rgb[-sample:, -sample:].reshape(-1, 3),
        ])
        bg_color = np.median(corner_pixels, axis=0)
        dist = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=2))
        candidate_bg = dist <= tolerance

        visited = np.zeros((height, width), dtype=bool)
        queue: deque[tuple[int, int]] = deque()

        for x in range(width):
            if candidate_bg[0, x]:
                queue.append((0, x))
            if candidate_bg[height - 1, x]:
                queue.append((height - 1, x))
        for y in range(height):
            if candidate_bg[y, 0]:
                queue.append((y, 0))
            if candidate_bg[y, width - 1]:
                queue.append((y, width - 1))

        while queue:
            y, x = queue.popleft()
            if visited[y, x] or not candidate_bg[y, x]:
                continue
            visited[y, x] = True
            if y > 0:
                queue.append((y - 1, x))
            if y < height - 1:
                queue.append((y + 1, x))
            if x > 0:
                queue.append((y, x - 1))
            if x < width - 1:
                queue.append((y, x + 1))

        alpha = np.full((height, width), 255, dtype=np.uint8)
        alpha[visited] = 0
        alpha_img = Image.fromarray(alpha, mode="L")
        if feather:
            alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=feather))

        image.putalpha(alpha_img)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")


register_pipeline_ui(CutoutVideoPipelineUI)
