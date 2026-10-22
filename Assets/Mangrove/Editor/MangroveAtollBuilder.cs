using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

static class MangroveAssets
{
    public const string Root = "Assets/Mangrove";
    public const string ModelFolder = Root + "/Models";
    public const string MaterialFolder = Root + "/Materials";
    public const string PlacementPath = Root + "/mangrove_placement.json";
    public const string BarkMaterial = MaterialFolder + "/Mangrove_Bark.mat";
    public const string FoliageMaterial = MaterialFolder + "/Mangrove_Foliage.mat";
    public const string LitterMaterial = MaterialFolder + "/Mangrove_Litter.mat";
    public const string GroundMaterial = MaterialFolder + "/Mangrove_Ground.mat";
    public const string WaterMaterial = MaterialFolder + "/Water_Mangrove.mat";
    public const string SeaWaterSource = "Assets/Water/Materials/Water_Atoll.mat";
    public const string SkyMaterial = MaterialFolder + "/Sky_Day.mat";
    public const string VolumeProfile = MaterialFolder + "/MangroveDay_Profile.asset";
    public const string ScenePath = "Assets/Scenes/MangroveAtoll.unity";
}

/// <summary>
/// Builds the mangrove atoll exported by BlenderTools/export_unity.py: ground, every placed tree
/// (as prefab instances of the LOD'd variant models), water with a murky inland zone, and a marker
/// where the dome camera goes. Open via Tools > Mangrove > Build Atoll Scene.
/// </summary>
static class MangroveAtollBuilder
{
    const string RootName = "MangroveAtoll";
    const float WaterSize = 400f;
    const int WaterResolution = 400;

    [Serializable] class Placement { public float seaLevel; public TreeInfo[] trees; public DomeCameraInfo domeCamera; public MurkInfo murk; }
    [Serializable] class TreeInfo { public string model; public float[] position; public float yaw; public float scale; }
    [Serializable] class DomeCameraInfo { public float[] position; public float[] forward; public float tiltDegrees; }
    [Serializable] class MurkInfo { public float[] radii; }

    [MenuItem("Tools/Mangrove/Build Atoll Scene")]
    static void BuildMenu() => Build();

    /// <summary>Builds (or rebuilds) the atoll in the active scene. Returns its root, or null on failure.</summary>
    static GameObject Build()
    {
        if (!File.Exists(MangroveAssets.PlacementPath))
        {
            Debug.LogError($"Mangrove: {MangroveAssets.PlacementPath} not found. Run BlenderTools/export_unity.py in Blender first.");
            return null;
        }
        var data = JsonUtility.FromJson<Placement>(File.ReadAllText(MangroveAssets.PlacementPath));

        EnsureMaterials(data);
        ReimportModels(); // lets the postprocessor pick up materials created just now

        var old = FindRoot(SceneManager.GetActiveScene(), RootName);
        if (old != null) Undo.DestroyObjectImmediate(old);
        var root = new GameObject(RootName);
        Undo.RegisterCreatedObjectUndo(root, "Build Mangrove Atoll");

        // Ground: terrain (with collider), rocks, leaf litter, debris
        var groundModel = AssetDatabase.LoadAssetAtPath<GameObject>(MangroveAssets.ModelFolder + "/Atoll_Ground.fbx");
        if (groundModel != null)
        {
            var ground = (GameObject)PrefabUtility.InstantiatePrefab(groundModel, root.transform);
            var terrain = ground.transform.Find("Atoll_Terrain");
            if (terrain != null) terrain.gameObject.AddComponent<MeshCollider>();
        }
        else Debug.LogWarning("Mangrove: Atoll_Ground.fbx not found.");

        // Trees
        var treeParent = new GameObject("Mangroves").transform;
        treeParent.SetParent(root.transform, false);
        var models = new Dictionary<string, GameObject>();
        int placed = 0, missing = 0;
        foreach (var t in data.trees)
        {
            if (!models.TryGetValue(t.model, out var model))
                models[t.model] = model = AssetDatabase.LoadAssetAtPath<GameObject>($"{MangroveAssets.ModelFolder}/{t.model}.fbx");
            if (model == null) { missing++; continue; }
            var tree = (GameObject)PrefabUtility.InstantiatePrefab(model, treeParent);
            tree.transform.SetLocalPositionAndRotation(ToVector(t.position), Quaternion.Euler(0, t.yaw, 0));
            tree.transform.localScale = Vector3.one * t.scale;
            placed++;
        }

        // Water: the project's Custom/Water shader with the murky zone switched on
        var water = new GameObject("Water", typeof(MeshFilter), typeof(MeshRenderer), typeof(WaterSurface));
        water.transform.SetParent(root.transform, false);
        water.transform.localPosition = new Vector3(0, data.seaLevel, 0);
        var surface = water.GetComponent<WaterSurface>();
        surface.size = WaterSize;
        surface.resolution = WaterResolution;
        surface.Rebuild();
        var waterRenderer = water.GetComponent<MeshRenderer>();
        waterRenderer.sharedMaterial = AssetDatabase.LoadAssetAtPath<Material>(MangroveAssets.WaterMaterial);
        waterRenderer.shadowCastingMode = ShadowCastingMode.Off;

        // Dome camera marker: forward axis = dome zenith (tilted toward the view), up = toward the back of the dome
        if (data.domeCamera?.position?.Length == 3)
        {
            var marker = new GameObject("DomeCameraMarker").transform;
            marker.SetParent(root.transform, false);
            marker.localPosition = ToVector(data.domeCamera.position);
            var forward = ToVector(data.domeCamera.forward);
            forward.y = 0;
            forward.Normalize();
            float elevation = (90f - data.domeCamera.tiltDegrees) * Mathf.Deg2Rad;
            var zenith = forward * Mathf.Cos(elevation) + Vector3.up * Mathf.Sin(elevation);
            var up = -forward * Mathf.Sin(elevation) + Vector3.up * Mathf.Cos(elevation);
            marker.localRotation = Quaternion.LookRotation(zenith, up);
        }

        EditorSceneManager.MarkSceneDirty(root.scene);
        Selection.activeGameObject = root;
        Debug.Log($"Mangrove: built atoll with {placed} trees" + (missing > 0 ? $" ({missing} skipped, model missing)" : "") + ".");
        return root;
    }

    /// <summary>
    /// Creates (or rebuilds) Assets/Scenes/MangroveAtoll.unity: the atoll, daytime sun, sky and haze,
    /// post-processing, and a working dome camera at the clearing. Leaves the currently open scenes alone.
    /// </summary>
    [MenuItem("Tools/Mangrove/Create Dome Scene")]
    static void CreateDomeScene()
    {
        var previous = SceneManager.GetActiveScene();
        var scene = SceneManager.GetSceneByPath(MangroveAssets.ScenePath);
        bool wasOpen = scene.isLoaded;
        if (!wasOpen)
            scene = File.Exists(MangroveAssets.ScenePath)
                ? EditorSceneManager.OpenScene(MangroveAssets.ScenePath, OpenSceneMode.Additive)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
        SceneManager.SetActiveScene(scene);
        try
        {
            foreach (var go in scene.GetRootGameObjects())
                if (go.name == SunName || go.name == VolumeName || go.name == DisplayCameraName)
                    UnityEngine.Object.DestroyImmediate(go);

            var root = Build();
            if (root == null) return;
            var sun = SetupDaylight();
            SetupDomeCamera(root, sun);
            EditorSceneManager.SaveScene(scene, MangroveAssets.ScenePath);
            Debug.Log($"Mangrove: saved {MangroveAssets.ScenePath}. Open it and press Play to see the dome view.");
        }
        finally
        {
            if (previous.IsValid()) SceneManager.SetActiveScene(previous);
            if (!wasOpen) EditorSceneManager.CloseScene(scene, true);
        }
    }

    const string SunName = "Sun";
    const string VolumeName = "Global Volume";
    const string DisplayCameraName = "Display Camera";

    static Light SetupDaylight()
    {
        // Same sun as the Blender scene: 45° high, warm.
        var sun = new GameObject(SunName).AddComponent<Light>();
        sun.type = LightType.Directional;
        sun.color = new Color(1f, 0.956f, 0.88f);
        sun.intensity = 2f;
        sun.shadows = LightShadows.Soft;
        sun.transform.rotation = Quaternion.LookRotation(new Vector3(0.406f, -0.707f, -0.579f));

        var sky = GetOrCreate(MangroveAssets.SkyMaterial, "Skybox/Procedural", m =>
        {
            m.SetFloat("_SunSize", 0.04f);
            m.SetFloat("_SunSizeConvergence", 5f);
            m.SetFloat("_AtmosphereThickness", 1.0f);
            m.SetColor("_SkyTint", new Color(0.5f, 0.55f, 0.6f));
            m.SetColor("_GroundColor", new Color(0.37f, 0.35f, 0.34f));
            m.SetFloat("_Exposure", 1.25f);
        });
        RenderSettings.skybox = sky;
        RenderSettings.sun = sun;
        RenderSettings.ambientMode = AmbientMode.Skybox;
        RenderSettings.ambientIntensity = 1f;
        RenderSettings.defaultReflectionMode = DefaultReflectionMode.Skybox;
        // humid coastal haze
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.ExponentialSquared;
        RenderSettings.fogDensity = 0.004f;
        RenderSettings.fogColor = new Color(0.66f, 0.76f, 0.84f);
        DynamicGI.UpdateEnvironment();

        var volume = new GameObject(VolumeName).AddComponent<Volume>();
        volume.isGlobal = true;
        volume.sharedProfile = GetOrCreateProfile();
        return sun;
    }

    static VolumeProfile GetOrCreateProfile()
    {
        var profile = AssetDatabase.LoadAssetAtPath<VolumeProfile>(MangroveAssets.VolumeProfile);
        if (profile != null) return profile;

        profile = ScriptableObject.CreateInstance<VolumeProfile>();
        AssetDatabase.CreateAsset(profile, MangroveAssets.VolumeProfile);
        var tonemapping = profile.Add<Tonemapping>(true);
        tonemapping.mode.Override(TonemappingMode.ACES);
        var bloom = profile.Add<Bloom>(true);
        bloom.threshold.Override(1.1f);
        bloom.intensity.Override(0.25f);
        var color = profile.Add<ColorAdjustments>(true);
        color.postExposure.Override(0.1f);
        color.saturation.Override(8f);
        foreach (var component in profile.components)
            AssetDatabase.AddObjectToAsset(component, profile);
        AssetDatabase.SaveAssets();
        return profile;
    }

    static void SetupDomeCamera(GameObject root, Light sun)
    {
        var marker = root.transform.Find("DomeCameraMarker");
        if (marker == null)
        {
            Debug.LogWarning("Mangrove: no DomeCameraMarker in the placement data; dome camera not created.");
            return;
        }
        var dome = new GameObject("DomeCamera").AddComponent<DomeMasterCamera>();
        dome.transform.SetParent(marker, false);
        dome.domeShader = Shader.Find("Hidden/Mangrove/DomeMaster");

        // The dome image is drawn as UI; this camera only clears the screen and hosts the audio listener.
        var display = new GameObject(DisplayCameraName, typeof(Camera), typeof(AudioListener));
        display.tag = "MainCamera";
        display.transform.SetPositionAndRotation(marker.position, Quaternion.LookRotation(Vector3.ProjectOnPlane(-marker.up, Vector3.up)));
        var cam = display.GetComponent<Camera>();
        cam.cullingMask = 0;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Color.black;
        cam.depth = 10;
    }

    static GameObject FindRoot(Scene scene, string name)
    {
        foreach (var go in scene.GetRootGameObjects())
            if (go.name == name) return go;
        return null;
    }

    static Vector3 ToVector(float[] v) => new Vector3(v[0], v[1], v[2]);

    static void EnsureMaterials(Placement data)
    {
        if (!AssetDatabase.IsValidFolder(MangroveAssets.MaterialFolder))
            AssetDatabase.CreateFolder(MangroveAssets.Root, "Materials");

        GetOrCreate(MangroveAssets.BarkMaterial, "Mangrove/Bark", null);
        GetOrCreate(MangroveAssets.FoliageMaterial, "Mangrove/Foliage", null);
        GetOrCreate(MangroveAssets.LitterMaterial, "Mangrove/Foliage", m =>
        {
            m.SetFloat("_Translucency", 0.15f);
            m.SetFloat("_Smoothness", 0.35f);
        });
        GetOrCreate(MangroveAssets.GroundMaterial, "Mangrove/Ground", null);
        GetOrCreate(MangroveAssets.WaterMaterial, "Custom/Water", m =>
        {
            var sea = AssetDatabase.LoadAssetAtPath<Material>(MangroveAssets.SeaWaterSource);
            if (sea != null) m.CopyPropertiesFromMaterial(sea);
            m.SetFloat("_MurkStrength", 1f);
            if (data.murk?.radii?.Length == 2)
                m.SetVector("_MurkRadii", new Vector4(data.murk.radii[0], data.murk.radii[1], 0, 0));
        });
        AssetDatabase.SaveAssets();
    }

    static Material GetOrCreate(string path, string shaderName, Action<Material> init)
    {
        var material = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (material != null) return material;
        var shader = Shader.Find(shaderName);
        if (shader == null)
        {
            Debug.LogError($"Mangrove: shader '{shaderName}' not found.");
            return null;
        }
        material = new Material(shader) { name = Path.GetFileNameWithoutExtension(path), enableInstancing = true };
        init?.Invoke(material);
        AssetDatabase.CreateAsset(material, path);
        return material;
    }

    static void ReimportModels()
    {
        foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { MangroveAssets.ModelFolder }))
            AssetDatabase.ImportAsset(AssetDatabase.GUIDToAssetPath(guid), ImportAssetOptions.ForceUpdate);
    }
}
