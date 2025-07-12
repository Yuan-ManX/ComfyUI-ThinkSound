from .nodes import LoadOThinkSoundVideo, LoadCaption, LoadCoTDescription, ThinkSound

NODE_CLASS_MAPPINGS = {
    "LoadOThinkSoundVideo": LoadOThinkSoundVideo,
    "LoadCaption": LoadCaption,
    "LoadCoTDescription": LoadCoTDescription,
    "ThinkSound": ThinkSound,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadOThinkSoundVideo": "LoadO ThinkSound Video",
    "LoadCaption": "Load Caption",
    "LoadCoTDescription": "Load CoT Description",
    "ThinkSound": "ThinkSound",
} 

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
