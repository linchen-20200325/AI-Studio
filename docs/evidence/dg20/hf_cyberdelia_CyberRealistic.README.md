---
license: creativeml-openrail-m
tags:
  - stable-diffusion
  - sd-1.5
  - text-to-image
  - photorealistic
  - cyberrealistic
  - image-generation
  - diffusers
model-index:
  - name: CyberRealistic v8.0
    results: []
---

# CyberRealistic

**CyberRealistic** is a photorealistic image generation model built upon the **Stable Diffusion 1.5 (SD 1.5)** architecture. Developed by [Cyberdelia](https://civitai.com/user/Cyberdelia), this model excels at producing lifelike portraits and scenes with minimal prompt engineering, making it ideal for creators seeking high-quality outputs without complex configurations.

---

## 🧠 Model Details

- **Model Type**: Text-to-Image Generation
- **Base Model**: Stable Diffusion 1.5 (SD 1.5)
- **Format**: `safetensors`
- **Version**: v8.0
- **Creator**: [Cyberdelia](https://civitai.com/user/Cyberdelia)
- **File Size**: ~6.3 GB
- **License**: [CreativeML Open RAIL++-M License](https://huggingface.co/spaces/CompVis/stable-diffusion-license)

---

## ✨ Features

- **Photorealism**: Generates highly detailed and realistic images, particularly effective for human subjects.
- **Ease of Use**: Designed for simplicity; achieves impressive results with straightforward prompts.
- **Integrated VAE**: Comes with a baked-in Variational Autoencoder for enhanced image quality.
- **Versatility**: Suitable for various applications, including portraits, fashion, and cinematic scenes.

---

## 🛠️ Recommended Settings

| Parameter       | Recommended Value                             |
|-----------------|------------------------------------------------|
| Sampling Steps  | 25–30                                          |
| Sampler         | DPM++ 2M Karras / Euler A                      |
| Resolution      | 512x512 (native), higher with Hires.fix        |
| Hires Upscaler  | 4x_NMKD-Siax_200k or 4x_NickelbackFS_72000_G   |
| CFG Scale       | 7.0–8.0                                        |
| VAE             | Already baked-in                               |

---

## 🧾 Example Prompts

> (masterpiece, best quality), ultra-detailed, realistic photo of a 22-year-old woman, natural lighting, depth of field, candid moment, color graded, RAW photo, soft cinematic bokeh

> (masterpiece, photorealistic), editorial fashion photo, close-up, dramatic side lighting, textured skin, shallow depth of field, soft shadows

---

## 📸 Example Outputs

![Sample 1](https://huggingface.co/cyberdelia/CyberRealistic/resolve/main/Cyber8_4.jpeg)
![Sample 2](https://huggingface.co/cyberdelia/CyberRealistic/resolve/main/Cyber8_16.jpeg)

---

## 🔗 Links

- [Civitai Model Page](https://civitai.com/models/15003/cyberrealistic)

---

## 🚫 Limitations

- May produce content that could be considered sensitive; use responsibly.
- Some prompts involving abstract or anime content may not perform as well due to realism-focused training.
- Lighting and skin may occasionally be too clean or smooth depending on sampling choices.

---

## ✅ License

This model is distributed under the **CreativeML Open RAIL++-M License**, which allows commercial and non-commercial use, with proper credit and no malicious usage.

> [License details](https://huggingface.co/spaces/CompVis/stable-diffusion-license)
