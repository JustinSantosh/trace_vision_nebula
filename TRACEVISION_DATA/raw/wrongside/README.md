# Wrong-side driving test clip

`ws01.mp4`: 32.6 s, 720×1280, 30 fps. A phone in a moving car on a Delhi flyover. A black SUV in the lanes beyond the concrete barrier comes towards the camera (front at about 0–9 s), passes it, and is seen from behind (about 14–18 s). Those lanes carry traffic the camera's way, so the SUV is driving the wrong way.

- **Source:** a downloaded social-media short. It is **not** the team's footage and its licence is unknown. It is in this public repo by the owner's choice (DECISIONS E20). Remove it if the uploader or the vehicle owner objects.
- **Use:** positive test case for the moving-camera wrong-side check (DECISIONS E19). Upload it in the app **under the name `ws01.mp4`**, so the `uploads` rule in `TRACEVISION_DATA/cameras/camera_rules.json` (layout `one_way`) applies. Expected result: one suspected violation, the SUV, with plate `HR11P2233` read. The plate isn't in the synthetic registry, so there's no match and no challan.
- It is not part of the evaluation set (`evaluation/clips.csv`), and `python -m tracevision.pipeline` does not process it.
