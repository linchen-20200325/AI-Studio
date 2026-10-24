---
language:
- en
library_name: diffusers
license: mit
pipeline_tag: image-to-image
---

# Arc2Face Model Card

<div align="center">

[**Project Page**](https://arc2face.github.io/) **|** [**Original Paper (ArXiv)**](https://arxiv.org/abs/2403.11641) **|** [**Expression Adapter Paper (ArXiv)**](http://arxiv.org/abs/2510.04706) **|** [**Code**](https://github.com/foivospar/Arc2Face) **|** [🤗 **Gradio demo**](https://huggingface.co/spaces/FoivosPar/Arc2Face)

</div>


🚀 **NEW (2025):** Arc2Face has been extended with a fine-grained **Expression Adapter** (see [below](#expression-adapter)), enabling the generation of any subject under any facial expression (even rare, asymmetric, subtle, or extreme ones). This extension is detailed in the paper [ID-Consistent, Precise Expression Generation with Blendshape-Guided Diffusion](http://arxiv.org/abs/2510.04706).

<div align="center">
<img src='https://huggingface.co/foivospar/Arc2Face/resolve/main/assets/exp_teaser.jpg'>
</div>

## Introduction

Originally, Arc2Face is an ID-conditioned face model designed to generate diverse, ID-consistent photos of a person given only its ArcFace ID-embedding.
It is trained on a restored version of the WebFace42M face recognition database, and is further fine-tuned on FFHQ and CelebA-HQ.

<div align="center">
<img src='https://huggingface.co/foivospar/Arc2Face/resolve/main/assets/samples_short.jpg'>
</div>

## Model Details

It consists of 2 components:
- encoder, a finetuned CLIP ViT-L/14 model
- arc2face, a finetuned UNet model

both of which are fine-tuned from [runwayml/stable-diffusion-v1-5](https://huggingface.co/runwayml/stable-diffusion-v1-5).
The encoder is tailored for projecting ID-embeddings to the CLIP latent space.
Arc2Face adapts the pre-trained backbone to the task of ID-to-face generation, conditioned solely on ID vectors.

## ControlNet (pose)

We also provide a ControlNet model trained on top of Arc2Face for pose control.

<div align="center">
<img src='https://huggingface.co/foivospar/Arc2Face/resolve/main/assets/controlnet_short.jpg'>
</div>

## Expression Adapter

Our [extension](http://arxiv.org/abs/2510.04706) combines Arc2Face with a custom IP-Adapter designed for generating ID-consistent images with precise expression control based on FLAME blendshape parameters. We also provide an optional Reference Adapter which can be used to condition the output directly on the input image, i.e. preserving the subject's appearance and background (to an extent). You can find more details in the report.

<div align="center">
<img src='https://huggingface.co/foivospar/Arc2Face/resolve/main/assets/arc2face_exp.jpg'>
</div>

## Download Core Models (Arc2Face)

The models can be downloaded directly from this repository or using python:
```python
from huggingface_hub import hf_hub_download

hf_hub_download(repo_id="FoivosPar/Arc2Face", filename="arc2face/config.json", local_dir="./models")
hf_hub_download(repo_id="FoivosPar/Arc2Face", filename="arc2face/diffusion_pytorch_model.safetensors", local_dir="./models")
hf_hub_download(repo_id="FoivosPar/Arc2Face", filename="encoder/config.json", local_dir="./models")
hf_hub_download(repo_id="FoivosPar/Arc2Face", filename="encoder/pytorch_model.bin", local_dir="./models")
```

Please check our [GitHub repository](https://github.com/foivospar/Arc2Face) for complete inference instructions, including the ControlNet and the Expression Adapter.

## Sample Usage with Diffusers (core model)

To use the Arc2Face model with the `diffusers` library, first load the pipeline components:

```python
from diffusers import (
    StableDiffusionPipeline,
    UNet2DConditionModel,
    DPMSolverMultistepScheduler,
)

from arc2face import CLIPTextModelWrapper, project_face_embs

import torch
from insightface.app import FaceAnalysis
from PIL import Image
import numpy as np

# Arc2Face is built upon SD1.5
# The repo below can be used instead of the now deprecated 'runwayml/stable-diffusion-v1-5'
base_model = 'stable-diffusion-v1-5/stable-diffusion-v1-5'

encoder = CLIPTextModelWrapper.from_pretrained(
    'models', subfolder="encoder", torch_dtype=torch.float16
)

unet = UNet2DConditionModel.from_pretrained(
    'models', subfolder="arc2face", torch_dtype=torch.float16
)

pipeline = StableDiffusionPipeline.from_pretrained(
        base_model,
        text_encoder=encoder,
        unet=unet,
        torch_dtype=torch.float16,
        safety_checker=None
    )
pipeline.scheduler = DPMSolverMultistepScheduler.from_config(pipeline.scheduler.config)
pipeline = pipeline.to('cuda')
```

Then, pick an image to extract the ID-embedding:

```python
app = FaceAnalysis(name='antelopev2', root='./', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))

img = np.array(Image.open('assets/examples/joacquin.png'))[:,:,::-1]

faces = app.get(img)
faces = sorted(faces, key=lambda x:(x['bbox'][2]-x['bbox'][0])*(x['bbox'][3]-x['bbox'][1]))[-1]  # select largest face (if more than one detected)
id_emb = torch.tensor(faces['embedding'], dtype=torch.float16)[None].cuda()
id_emb = id_emb/torch.norm(id_emb, dim=1, keepdim=True)   # normalize embedding
id_emb = project_face_embs(pipeline, id_emb)    # pass through the encoder
```

<div align="center">
<img src='https://huggingface.co/foivospar/Arc2Face/resolve/main/assets/joacquin.png' style='width:25%;'>
</div>

Finally, generate images:
```python
num_images = 4
images = pipeline(prompt_embeds=id_emb, num_inference_steps=25, guidance_scale=3.0, num_images_per_prompt=num_images).images
```
<div align="center">
<img src='https://huggingface.co/foivospar/Arc2Face/resolve/main/assets/samples.jpg'>
</div>

## Limitations and Bias

- Only one person per image can be generated.
- Poses are constrained to the frontal hemisphere, similar to FFHQ images.
- The model may reflect the biases of the training data or the ID encoder.

## Citation

If you find Arc2Face useful for your research, please consider citing us:

**BibTeX for Arc2Face:**
```bibtex
@inproceedings{paraperas2024arc2face,
      title={Arc2Face: A Foundation Model for ID-Consistent Human Faces}, 
      author={Paraperas Papantoniou, Foivos and Lattas, Alexandros and Moschoglou, Stylianos and Deng, Jiankang and Kainz, Bernhard and Zafeiriou, Stefanos},
      booktitle={Proceedings of the European Conference on Computer Vision (ECCV)},
      year={2024}
}
```

Additionally, if you use the Expression Adapter, please also cite the extension:

**BibTeX for Expression Adapter:**
```bibtex
@inproceedings{paraperas2025arc2face_exp,
      title={ID-Consistent, Precise Expression Generation with Blendshape-Guided Diffusion}, 
      author={Paraperas Papantoniou, Foivos and Zafeiriou, Stefanos},
      booktitle={Proceedings of the IEEE/CVF International Conference on Computer Vision (ICCV) Workshops},
      year={2025}
}
```