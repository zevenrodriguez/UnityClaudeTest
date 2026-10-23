using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

/// <summary>
/// Fulldome camera: renders five 90° faces around this transform (forward = dome zenith,
/// up = back of the dome) and stitches them into an equidistant fisheye domemaster image.
/// Shows it full screen in Play mode and can record a PNG sequence for dome playback.
/// </summary>
public class DomeMasterCamera : MonoBehaviour
{
    [Tooltip("Hidden/Mangrove/DomeMaster; assigned by the scene builder so it's included in builds.")]
    public Shader domeShader;

    [Range(90f, 250f)] public float fieldOfView = 180f;
    [Tooltip("Size of each of the five camera faces.")]
    public int faceResolution = 1024;
    [Tooltip("Size of the square domemaster image.")]
    public int outputResolution = 2048;
    public float nearClip = 0.05f;
    public float farClip = 2000f;
    public bool postProcessing = true;
    public bool showOnScreen = true;

    [Header("Recording")]
    public bool recordFrames;
    public int recordFrameRate = 30;
    [Tooltip("Relative to the project folder (or the player's data folder in a build).")]
    public string recordFolder = "DomeCaptures";

    public RenderTexture Output { get; private set; }

    readonly Camera[] _faces = new Camera[5];
    readonly RenderTexture[] _faceTextures = new RenderTexture[5];
    Material _material;
    GameObject _canvas;
    int _frame;

    // forward and up of each face, in the dome's local space
    static readonly Vector3[] FaceForward = { Vector3.forward, Vector3.right, Vector3.left, Vector3.up, Vector3.down };
    static readonly Vector3[] FaceUp = { Vector3.up, Vector3.forward, Vector3.forward, Vector3.forward, Vector3.forward };

    void OnEnable()
    {
        if (!Application.isPlaying) return;
        if (domeShader == null) domeShader = Shader.Find("Hidden/Mangrove/DomeMaster");
        _material = new Material(domeShader) { hideFlags = HideFlags.DontSave };

        Output = new RenderTexture(outputResolution, outputResolution, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
        {
            name = "DomeMaster"
        };

        for (int i = 0; i < 5; i++)
        {
            _faceTextures[i] = new RenderTexture(faceResolution, faceResolution, 24, RenderTextureFormat.DefaultHDR) { name = $"DomeFace{i}" };
            var go = new GameObject($"DomeFace{i}") { hideFlags = HideFlags.DontSave };
            go.transform.SetParent(transform, false);
            go.transform.localRotation = Quaternion.LookRotation(FaceForward[i], FaceUp[i]);
            var cam = go.AddComponent<Camera>();
            cam.fieldOfView = 90f;
            cam.aspect = 1f;
            cam.nearClipPlane = nearClip;
            cam.farClipPlane = farClip;
            cam.targetTexture = _faceTextures[i];
            var data = cam.GetUniversalAdditionalCameraData();
            data.renderPostProcessing = postProcessing;
            data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            data.dithering = true; // avoids banding in the large sky gradients a dome shows
            _faces[i] = cam;
            _material.SetTexture($"_Face{i}", _faceTextures[i]);
        }

        if (showOnScreen) CreateScreenView();
        if (recordFrames) Time.captureFramerate = recordFrameRate;
        StartCoroutine(StitchEveryFrame());
    }

    void OnDisable()
    {
        StopAllCoroutines();
        if (recordFrames) Time.captureFramerate = 0;
        foreach (var cam in _faces)
            if (cam != null) Destroy(cam.gameObject);
        foreach (var rt in _faceTextures)
            if (rt != null) rt.Release();
        if (Output != null) Output.Release();
        if (_canvas != null) Destroy(_canvas);
        if (_material != null) Destroy(_material);
    }

    IEnumerator StitchEveryFrame()
    {
        var wait = new WaitForEndOfFrame();
        while (true)
        {
            yield return wait; // all cameras have rendered this frame
            Stitch();
            if (recordFrames) SaveFrame();
        }
    }

    void Stitch()
    {
        var right = new Vector4[5];
        var up = new Vector4[5];
        var forward = new Vector4[5];
        for (int i = 0; i < 5; i++)
        {
            var t = _faces[i].transform;
            right[i] = t.right;
            up[i] = t.up;
            forward[i] = t.forward;
        }
        _material.SetVectorArray("_FaceRight", right);
        _material.SetVectorArray("_FaceUp", up);
        _material.SetVectorArray("_FaceForward", forward);
        _material.SetVector("_DomeRight", transform.right);
        _material.SetVector("_DomeUp", transform.up);
        _material.SetVector("_DomeForward", transform.forward);
        _material.SetFloat("_HalfFov", fieldOfView * 0.5f * Mathf.Deg2Rad);
        Graphics.Blit(null, Output, _material);
    }

    [ContextMenu("Save Domemaster Frame")]
    public void SaveFrame()
    {
        if (Output == null) return;
        var previous = RenderTexture.active;
        RenderTexture.active = Output;
        var image = new Texture2D(Output.width, Output.height, TextureFormat.RGB24, false);
        image.ReadPixels(new Rect(0, 0, Output.width, Output.height), 0, 0);
        image.Apply();
        RenderTexture.active = previous;

        var folder = Path.Combine(Path.GetDirectoryName(Application.dataPath) ?? ".", recordFolder);
        Directory.CreateDirectory(folder);
        File.WriteAllBytes(Path.Combine(folder, $"dome_{_frame++:D5}.png"), image.EncodeToPNG());
        Destroy(image);
    }

    void CreateScreenView()
    {
        _canvas = new GameObject("DomeMasterView") { hideFlags = HideFlags.DontSave };
        var canvas = _canvas.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 100;

        var view = new GameObject("Image", typeof(RectTransform)) { hideFlags = HideFlags.DontSave };
        view.transform.SetParent(_canvas.transform, false);
        var rect = (RectTransform)view.transform;
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        view.AddComponent<RawImage>().texture = Output;
        var fitter = view.AddComponent<AspectRatioFitter>();
        fitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
        fitter.aspectRatio = 1f;
    }
}
