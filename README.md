# ComfyUI-ThinkSound

ComfyUI-ThinkSound is now available in ComfyUI, [ThinkSound](https://github.com/FunAudioLLM/ThinkSound) is a unified Any2Audio generation framework with flow matching guided by Chain-of-Thought (CoT) reasoning.



## Installation

1. Make sure you have ComfyUI installed

2. Clone this repository into your ComfyUI's custom_nodes directory:
```
cd ComfyUI/custom_nodes
git clone https://github.com/Yuan-ManX/ComfyUI-ThinkSound.git
```

3. Install dependencies:
```
cd ComfyUI-ThinkSound

# Install dependencies
pip install -r requirements.txt
conda install -y -c conda-forge 'ffmpeg<7'
```



## Model

### Download Pretrained Models

```
# Download pretrained weights https://huggingface.co/liuhuadai/ThinkSound to Directory ckpts/
# model weights can be also downloaded from https://www.modelscope.cn/models/iic/ThinkSound
git lfs install
git clone https://huggingface.co/liuhuadai/ThinkSound ckpts
```
