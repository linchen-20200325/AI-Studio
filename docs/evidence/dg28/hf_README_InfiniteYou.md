---
license: cc-by-nc-4.0
language:
- en
library_name: infinite-you
pipeline_tag: text-to-image
tags:
- Text-to-Image
- FLUX.1-dev
- image-generation
- Diffusion-Transformer
- subject-personalization
base_model: black-forest-labs/FLUX.1-dev
---


# InfiniteYou Model Card

<div style="display:flex;justify-content: center">
<a href="https://bytedance.github.io/InfiniteYou"><img src="https://img.shields.io/static/v1?label=Project&message=Page&color=blue&logo=github-pages"></a> &ensp;
<a href="https://arxiv.org/abs/2503.16418"><img src="https://img.shields.io/static/v1?label=ArXiv&message=Paper&color=darkred&logo=arxiv"></a> &ensp;
<a href="https://github.com/bytedance/InfiniteYou"><img src="https://img.shields.io/static/v1?label=GitHub&message=Code&color=green&logo=github"></a> &ensp;
<a href="https://github.com/bytedance/ComfyUI_InfiniteYou"><img src="https://img.shields.io/static/v1?label=%E2%9A%99%EF%B8%8F%20ComfyUI&message=Node&color=purple"></a> &ensp;
<a href="https://huggingface.co/spaces/ByteDance/InfiniteYou-FLUX"><img src="https://img.shields.io/static/v1?label=%F0%9F%A4%97%20Hugging%20Face&message=Demo&color=orange"></a> &ensp;
</div>

![teaser](./assets/teaser.jpg)

This repository provides the official models for the following paper:

[**InfiniteYou: Flexible Photo Recrafting While Preserving Your Identity**](https://arxiv.org/abs/2503.16418)<br />
[Liming Jiang](https://liming-jiang.com/), 
[Qing Yan](https://scholar.google.com/citations?user=0TIYjPAAAAAJ), 
[Yumin Jia](https://www.linkedin.com/in/yuminjia/), 
[Zichuan Liu](https://scholar.google.com/citations?user=-H18WY8AAAAJ), 
[Hao Kang](https://scholar.google.com/citations?user=VeTCSyEAAAAJ), 
[Xin Lu](https://scholar.google.com/citations?user=mFC0wp8AAAAJ)<br />
ByteDance Intelligent Creation<br />
**ICCV 2025 (<span style="color:#F44336">Highlight</span>)**

> **Abstract:** Achieving flexible and high-fidelity identity-preserved image generation remains formidable, particularly with advanced Diffusion Transformers (DiTs) like FLUX. We introduce **InfiniteYou (InfU)**, one of the earliest robust frameworks leveraging DiTs for this task. InfU addresses significant issues of existing methods, such as insufficient identity similarity, poor text-image alignment, and low generation quality and aesthetics. Central to InfU is InfuseNet, a component that injects identity features into the DiT base model via residual connections, enhancing identity similarity while maintaining generation capabilities. A multi-stage training strategy, including pretraining and supervised fine-tuning (SFT) with synthetic single-person-multiple-sample (SPMS) data, further improves text-image alignment, ameliorates image quality, and alleviates face copy-pasting. Extensive experiments demonstrate that InfU achieves state-of-the-art performance, surpassing existing baselines. In addition, the plug-and-play design of InfU ensures compatibility with various existing methods, offering a valuable contribution to the broader community.


## 🔧 Installation and Usage

Please clone our [GitHub code repository](https://github.com/bytedance/InfiniteYou) and follow the [detailed instructions](https://github.com/bytedance/InfiniteYou#-requirements-and-installation) to install and use the released models for local inference.

We appreciate the GPU grant from the Hugging Face team. 
You can also try our [InfiniteYou-FLUX Hugging Face demo](https://huggingface.co/spaces/ByteDance/InfiniteYou-FLUX) online.


## 💡 Important Usage Tips

- We released two model variants of InfiniteYou-FLUX v1.0: [aes_stage2](https://huggingface.co/ByteDance/InfiniteYou/tree/main/infu_flux_v1.0/aes_stage2) and [sim_stage1](https://huggingface.co/ByteDance/InfiniteYou/tree/main/infu_flux_v1.0/sim_stage1). The `aes_stage2` is our model after stage-2 SFT, which is used by default for better text-image alignment and aesthetics. If you wish to achieve higher ID similarity, please try `sim_stage1`.

- To better fit specific personal needs, we find that two arguments are highly useful to adjust in our [code](https://github.com/bytedance/InfiniteYou): `--infusenet_conditioning_scale` (default: `1.0`) and `--infusenet_guidance_start` (default: `0.0`). Usually, you may NOT need to adjust them. If necessary, start by trying a slightly larger `--infusenet_guidance_start` (*e.g.*, `0.1`) only (especially helpful for `sim_stage1`). If still not satisfactory, then try a slightly smaller `--infusenet_conditioning_scale` (*e.g.*, `0.9`).

- We also provided two LoRAs ([Realism](https://civitai.com/models/631986?modelVersionId=706528) and [Anti-blur](https://civitai.com/models/675581/anti-blur-flux-lora)) to enable additional usage flexibility. If needed, try `Realism` only first.  They are *entirely optional*, which are examples to try but are NOT used in our paper.

- If the generated gender is not preferred, try adding specific words in the text prompt, such as 'a man', 'a woman', *etc*. We encourage using inclusive and respectful language.


## 🏰 Model Zoo

| InfiniteYou Version | Model Version | Base Model Trained with | Description |  
| :---: | :---: | :---: | :---: |
| [InfiniteYou-FLUX v1.0](https://huggingface.co/ByteDance/InfiniteYou) | [aes_stage2](https://huggingface.co/ByteDance/InfiniteYou/tree/main/infu_flux_v1.0/aes_stage2) | [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) | Stage-2 model after SFT. Better text-image alignment and aesthetics. |
| [InfiniteYou-FLUX v1.0](https://huggingface.co/ByteDance/InfiniteYou) | [sim_stage1](https://huggingface.co/ByteDance/InfiniteYou/tree/main/infu_flux_v1.0/sim_stage1) | [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) | Stage-1 model before SFT. Higher identity similarity. |


## 🆚 Comparison with State-of-the-Art Relevant Methods

![comparative_results](./assets/comparative_results.jpg)

Qualitative comparison results of InfU with the state-of-the-art baselines, FLUX.1-dev IP-Adapter and PuLID-FLUX. The identity similarity and text-image alignment of the results generated by FLUX.1-dev IP-Adapter (IPA) are inadequate. PuLID-FLUX generates images with decent identity similarity. However, it suffers from poor text-image alignment (Columns 1, 2, 4), and the image quality (e.g., bad hands in Column 5) and aesthetic appeal are degraded. In addition, the face copy-paste issue of PuLID-FLUX is evident (Column 5). In comparison, the proposed InfU outperforms the baselines across all dimensions.


## ⚙️ Plug-and-Play Property with Off-the-Shelf Popular Approaches

![plug_and_play](./assets/plug_and_play.jpg)

InfU features a desirable plug-and-play design, compatible with many existing methods. It naturally supports base model replacement with any variants of FLUX.1-dev, such as FLUX.1-schnell for more efficient generation (e.g., in 4 steps). The compatibility with ControlNets and LoRAs provides more controllability and flexibility for customized tasks. Notably, the compatibility with OminiControl extends our potential for multi-concept personalization, such as interacted identity (ID) and object personalized generation. InfU is also compatible with IP-Adapter (IPA) for stylization of personalized images, producing decent results when injecting style references via IPA. Our plug-and-play feature may extend to even more approaches, providing valuable contributions to the broader community.


## 📜 Disclaimer and Licenses

The images used in this repository and related demos are sourced from consented subjects or generated by the models. 
These pictures are intended solely to showcase the capabilities of our research. If you have any concerns, please feel free to contact us, and we will promptly remove any inappropriate content.

Our model is released under the [Creative Commons Attribution-NonCommercial 4.0 International Public License](./LICENSE) for academic research purposes only. Any manual or automatic downloading of the face models from [InsightFace](https://github.com/deepinsight/insightface), the [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) base model, LoRAs ([Realism](https://civitai.com/models/631986?modelVersionId=706528) and [Anti-blur](https://civitai.com/models/675581/anti-blur-flux-lora)), *etc.*, must follow their original licenses and be used only for academic research purposes.

This research aims to positively impact the field of Generative AI. Any usage of this method must be responsible and comply with local laws. The developers do not assume any responsibility for any potential misuse.


## 📖 Citation

If you find InfiniteYou useful for your research or applications, please cite our paper:

```bibtex
@inproceedings{jiang2025infiniteyou,
  title={{InfiniteYou}: Flexible Photo Recrafting While Preserving Your Identity},
  author={Jiang, Liming and Yan, Qing and Jia, Yumin and Liu, Zichuan and Kang, Hao and Lu, Xin},
  booktitle={ICCV},
  year={2025}
}
```

We also appreciate it if you could give a star ⭐ to our [Github repository](https://github.com/bytedance/InfiniteYou). Thanks a lot!
