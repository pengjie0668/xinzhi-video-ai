# API 使用

芯智未来 AI 视频引擎 提供完整的 Python API，方便集成到你的项目中。

---

## 快速开始

```python
from xinzhi_video_ai.service import XinzhiVideoAICore
import asyncio

async def main():
    # 初始化
    xinzhi_ai = XinzhiVideoAICore()
    await xinzhi_ai.initialize()
    
    # 生成视频
    result = await xinzhi_ai.generate_video(
        text="为什么要养成阅读习惯",
        mode="generate",
        n_scenes=5
    )
    
    print(f"视频已生成: {result.video_path}")

# 运行
asyncio.run(main())
```

---

## API 参考

详细 API 文档请查看 [API 概览](../reference/api-overview.md)。

---

## 示例

更多使用示例请参考项目的 `examples/` 目录。

