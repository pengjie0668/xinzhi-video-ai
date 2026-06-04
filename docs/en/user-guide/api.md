# API Usage

Xinzhi Video AI provides a complete Python API for easy integration into your projects.

---

## Quick Start

```python
from xinzhi_video_ai.service import XinzhiVideoAICore
import asyncio

async def main():
    # Initialize
    xinzhi_ai = XinzhiVideoAICore()
    await xinzhi_ai.initialize()
    
    # Generate video
    result = await xinzhi_ai.generate_video(
        text="Why develop a reading habit",
        mode="generate",
        n_scenes=5
    )
    
    print(f"Video generated: {result.video_path}")

# Run
asyncio.run(main())
```

---

## API Reference

For detailed API documentation, see [API Overview](../reference/api-overview.md).

---

## Examples

For more usage examples, check the `examples/` directory in the project.

