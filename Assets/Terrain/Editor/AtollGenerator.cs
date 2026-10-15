using System;
using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Generates a realistic coral atoll: a ring of reef and sandy islets (motus)
/// enclosing a shallow lagoon, with a steep drop-off to the open ocean.
/// Sea level is world y = 0. Open via Tools > Terrain > Generate Atoll.
/// </summary>
public class AtollGenerator : EditorWindow
{
    const string Root = "Assets/Terrain";
    const string TextureFolder = Root + "/Textures";
    const string RootObjectName = "Atoll";

    [SerializeField] int seed = 1234;
    [SerializeField] float terrainSize = 1200f;
    [SerializeField] int heightmapResolution = 1025;
    [SerializeField] float ringRadius = 320f;
    [SerializeField] float reefWidth = 140f;
    [SerializeField] float outerSlopeWidth = 120f;
    [SerializeField] float innerSlopeWidth = 70f;
    [SerializeField] float oceanDepth = 40f;
    [SerializeField] float lagoonDepth = 9f;
    [SerializeField] float isletHeight = 3.5f;
    [SerializeField] float isletCoverage = 0.55f;
    [SerializeField] bool createOcean = true;

    // Per-seed noise offsets
    float _o1, _o2, _o3, _o4, _o5, _o6, _o7;

    [MenuItem("Tools/Terrain/Generate Atoll")]
    static void Open() => GetWindow<AtollGenerator>("Atoll Generator");

    void OnGUI()
    {
        EditorGUILayout.LabelField("Shape", EditorStyles.boldLabel);
        seed = EditorGUILayout.IntField("Seed", seed);
        terrainSize = EditorGUILayout.FloatField("Terrain Size (m)", terrainSize);
        heightmapResolution = EditorGUILayout.IntPopup("Heightmap Resolution", heightmapResolution,
            new[] { "513", "1025", "2049" }, new[] { 513, 1025, 2049 });
        ringRadius = EditorGUILayout.FloatField("Ring Radius (m)", ringRadius);
        reefWidth = EditorGUILayout.FloatField("Reef Width (m)", reefWidth);
        outerSlopeWidth = EditorGUILayout.FloatField("Outer Slope Width (m)", outerSlopeWidth);
        innerSlopeWidth = EditorGUILayout.FloatField("Lagoon Slope Width (m)", innerSlopeWidth);

        EditorGUILayout.Space();
        EditorGUILayout.LabelField("Depths & Heights", EditorStyles.boldLabel);
        oceanDepth = EditorGUILayout.FloatField("Ocean Depth (m)", oceanDepth);
        lagoonDepth = EditorGUILayout.FloatField("Lagoon Depth (m)", lagoonDepth);
        isletHeight = EditorGUILayout.FloatField("Islet Height (m)", isletHeight);
        isletCoverage = EditorGUILayout.Slider("Islet Coverage", isletCoverage, 0f, 1f);

        EditorGUILayout.Space();
        createOcean = EditorGUILayout.Toggle("Create Ocean Surface", createOcean);

        float extent = ringRadius * 1.15f + reefWidth * 0.5f + outerSlopeWidth;
        if (extent > terrainSize * 0.5f)
            EditorGUILayout.HelpBox("The reef may reach the terrain edge. Increase Terrain Size or reduce Ring Radius.", MessageType.Warning);

        EditorGUILayout.Space();
        if (GUILayout.Button("Generate", GUILayout.Height(32)))
            Generate();
    }

    void Generate()
    {
        try
        {
            EnsureFolder(Root);
            EnsureFolder(TextureFolder);

            var rng = new System.Random(seed);
            _o1 = (float)rng.NextDouble() * 1000f; _o2 = (float)rng.NextDouble() * 1000f;
            _o3 = (float)rng.NextDouble() * 1000f; _o4 = (float)rng.NextDouble() * 1000f;
            _o5 = (float)rng.NextDouble() * 1000f; _o6 = (float)rng.NextDouble() * 1000f;
            _o7 = (float)rng.NextDouble() * 1000f;

            EditorUtility.DisplayProgressBar("Atoll", "Creating ground textures...", 0.05f);
            var layers = AtollTextures.GetOrCreateLayers(TextureFolder);

            EditorUtility.DisplayProgressBar("Atoll", "Sculpting heightmap...", 0.3f);
            var data = BuildTerrainData();

            EditorUtility.DisplayProgressBar("Atoll", "Painting terrain...", 0.7f);
            data.terrainLayers = layers;
            PaintSplatmap(data);

            string dataPath = Root + "/Atoll_TerrainData.asset";
            AssetDatabase.DeleteAsset(dataPath);
            AssetDatabase.CreateAsset(data, dataPath);

            EditorUtility.DisplayProgressBar("Atoll", "Building scene objects...", 0.9f);
            BuildSceneObjects(data);
            AssetDatabase.SaveAssets();
        }
        finally
        {
            EditorUtility.ClearProgressBar();
        }
    }

    // ---------------- Heightmap ----------------

    float HeightRange => oceanDepth + isletHeight * 1.5f + 2f;

    TerrainData BuildTerrainData()
    {
        int res = heightmapResolution;
        var data = new TerrainData();
        data.heightmapResolution = res; // must be set before size
        data.size = new Vector3(terrainSize, HeightRange, terrainSize);

        var heights = new float[res, res];
        for (int z = 0; z < res; z++)
        {
            float wz = (z / (float)(res - 1) - 0.5f) * terrainSize;
            for (int x = 0; x < res; x++)
            {
                float wx = (x / (float)(res - 1) - 0.5f) * terrainSize;
                float h = SampleHeight(wx, wz);
                heights[z, x] = Mathf.Clamp01((h + oceanDepth) / HeightRange);
            }
        }
        data.SetHeights(0, 0, heights);
        return data;
    }

    /// <summary>Height in meters relative to sea level at world position (x, z).</summary>
    float SampleHeight(float x, float z)
    {
        // Domain warp so the ring isn't a perfect circle.
        float warp = ringRadius * 0.08f;
        float px = x + (Fbm(x * 0.004f + _o1, z * 0.004f + _o2, 3) - 0.5f) * 2f * warp;
        float pz = z + (Fbm(x * 0.004f + _o3, z * 0.004f + _o4, 3) - 0.5f) * 2f * warp;

        float r = Mathf.Sqrt(px * px + pz * pz);
        float theta = Mathf.Atan2(pz, px);
        float cx = Mathf.Cos(theta), sz = Mathf.Sin(theta);

        float ringR = ringRadius * (1f + 0.3f * (Fbm(cx * 1.5f + _o5, sz * 1.5f + _o5, 3) - 0.5f));
        float d = r - ringR; // positive = toward open ocean
        float reefHalf = reefWidth * 0.5f;

        // Reef flat sits just below the surface.
        float reefFlat = -0.9f + (Fbm(x * 0.02f + _o6, z * 0.02f + _o6, 3) - 0.5f) * 0.6f;

        float h;
        if (d >= 0f)
        {
            // Outer reef: abrupt drop-off that eases into the ocean floor.
            float t = Mathf.Clamp01((d - reefHalf) / outerSlopeWidth);
            t = 1f - (1f - t) * (1f - t);
            float floor = -oceanDepth * 0.92f + (Fbm(x * 0.006f + _o7, z * 0.006f, 3) - 0.5f) * 6f;
            h = Mathf.Lerp(reefFlat, floor, t);
        }
        else
        {
            // Lagoon: gentler slope down to a sandy floor with scattered patch reefs.
            float t = SmoothStep(0f, 1f, (-d - reefHalf) / innerSlopeWidth);
            float floor = -lagoonDepth + (Fbm(x * 0.008f + _o2, z * 0.008f + _o3, 3) - 0.5f) * 4f;
            h = Mathf.Lerp(reefFlat, floor, t);

            float patch = SmoothStep(0.62f, 0.72f, Fbm(x * 0.015f + _o4, z * 0.015f + _o1, 3)) * t;
            h = Mathf.Lerp(h, -1.4f + reefFlat * 0.3f, patch * 0.85f);
        }

        // Islets (motus) along the reef, separated by channels.
        float threshold = Mathf.Lerp(0.72f, 0.32f, isletCoverage);
        float motuNoise = Fbm(cx * 3f + _o6, sz * 3f + _o7, 4) + (Fbm(x * 0.01f + _o5, z * 0.01f, 2) - 0.5f) * 0.15f;
        float mask = SmoothStep(threshold - 0.04f, threshold + 0.04f, motuNoise);
        if (mask > 0f)
        {
            float landHalf = reefHalf * (0.35f + 0.3f * Fbm(x * 0.006f + _o3, z * 0.006f + _o7, 2));
            float t = 1f - Mathf.Abs(d - reefHalf * 0.15f) / landHalf;
            float bump = SmoothStep(0f, 0.45f, t);
            float isletTop = isletHeight * (0.6f + 0.6f * Fbm(x * 0.01f + _o1, z * 0.01f + _o4, 2));
            h = Mathf.Lerp(h, isletTop, bump * mask);
        }

        // Small-scale undulation.
        h += (Fbm(x * 0.08f + _o5, z * 0.08f + _o6, 2) - 0.5f) * 0.3f;
        return h;
    }

    // ---------------- Splatmap ----------------
    // Layer order matches AtollTextures: 0 Sand, 1 Seafloor, 2 Vegetation, 3 Reef

    void PaintSplatmap(TerrainData data)
    {
        int res = 1024;
        data.alphamapResolution = res;
        data.baseMapResolution = 1024;
        var alpha = new float[res, res, 4];

        for (int z = 0; z < res; z++)
        {
            float nz = z / (float)(res - 1);
            for (int x = 0; x < res; x++)
            {
                float nx = x / (float)(res - 1);
                float h = data.GetInterpolatedHeight(nx, nz) - oceanDepth;
                float steep = data.GetSteepness(nx, nz);
                float wx = nx * terrainSize, wz = nz * terrainSize;
                float n1 = Fbm(wx * 0.03f + _o1, wz * 0.03f + _o2, 3);
                float n2 = Fbm(wx * 0.012f + _o3, wz * 0.012f + _o4, 3);

                float vegetation = SmoothStep(1.4f, 2.4f, h + (n1 - 0.5f) * 1.4f) * (1f - SmoothStep(22f, 35f, steep));
                float dryBeach = SmoothStep(-1.3f, -0.2f, h) * (1f - vegetation);
                float underwater = 1f - dryBeach - vegetation;

                // Coral/rubble on reef flats (patchy), steep outer walls and cliffs.
                float reefFlat = SmoothStep(-4f, -2f, h) * SmoothStep(0.42f, 0.58f, n2);
                float walls = SmoothStep(14f, 26f, steep);
                float reef = Mathf.Clamp01(Mathf.Max(reefFlat, walls)) * underwater;
                float seafloor = underwater - reef;

                // Rock also shows on steep slopes above water.
                float rockAbove = SmoothStep(30f, 45f, steep) * (1f - underwater);
                vegetation *= 1f - rockAbove;
                dryBeach *= 1f - rockAbove;
                reef += rockAbove;

                float sum = dryBeach + seafloor + vegetation + reef + 1e-5f;
                alpha[z, x, 0] = dryBeach / sum;
                alpha[z, x, 1] = seafloor / sum;
                alpha[z, x, 2] = vegetation / sum;
                alpha[z, x, 3] = reef / sum;
            }
        }
        data.SetAlphamaps(0, 0, alpha);
    }

    // ---------------- Scene ----------------

    void BuildSceneObjects(TerrainData data)
    {
        var existing = GameObject.Find(RootObjectName);
        if (existing != null) Undo.DestroyObjectImmediate(existing);

        var root = new GameObject(RootObjectName);

        var terrainGo = Terrain.CreateTerrainGameObject(data);
        terrainGo.name = "Atoll Terrain";
        terrainGo.transform.SetParent(root.transform, false);
        terrainGo.transform.position = new Vector3(-terrainSize * 0.5f, -oceanDepth, -terrainSize * 0.5f);

        var terrain = terrainGo.GetComponent<Terrain>();
        terrain.materialTemplate = GetOrCreateTerrainMaterial();
        terrain.drawInstanced = true;
        terrain.heightmapPixelError = 2f;
        terrain.basemapDistance = 400f;

        if (createOcean)
        {
            var ocean = new GameObject("Ocean", typeof(MeshFilter), typeof(MeshRenderer), typeof(WaterSurface));
            ocean.transform.SetParent(root.transform, false);
            var surface = ocean.GetComponent<WaterSurface>();
            surface.size = terrainSize + 200f;
            surface.resolution = 768;
            surface.Rebuild();

            var renderer = ocean.GetComponent<MeshRenderer>();
            renderer.sharedMaterial = GetOrCreateOceanMaterial();
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        Undo.RegisterCreatedObjectUndo(root, "Generate Atoll");
        Selection.activeGameObject = root;
        SceneView.lastActiveSceneView?.FrameSelected();
    }

    static Material GetOrCreateTerrainMaterial()
    {
        const string path = Root + "/AtollTerrain.mat";
        var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (mat != null) return mat;

        var shader = Shader.Find("Universal Render Pipeline/Terrain/Lit");
        if (shader == null) return null; // fall back to the pipeline default
        mat = new Material(shader);
        AssetDatabase.CreateAsset(mat, path);
        return mat;
    }

    static Material GetOrCreateOceanMaterial()
    {
        const string path = "Assets/Water/Materials/Water_Atoll.mat";
        var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (mat != null) return mat;

        var shader = Shader.Find("Custom/Water");
        if (shader == null)
        {
            Debug.LogError("Water shader 'Custom/Water' not found.");
            return null;
        }

        EnsureFolder("Assets/Water/Materials");
        mat = new Material(shader);
        // Clear tropical water: turquoise over sand, deep navy past the drop-off.
        mat.SetColor("_ShallowColor", new Color(0.25f, 0.85f, 0.78f, 0.12f));
        mat.SetColor("_DeepColor", new Color(0.01f, 0.09f, 0.26f, 0.97f));
        mat.SetFloat("_DepthMaxDistance", 22f);
        // Gentle swell; keeps troughs from exposing the reef flat too much.
        mat.SetVector("_WaveA", new Vector4(1f, 0.2f, 0.05f, 40f));
        mat.SetVector("_WaveB", new Vector4(0.3f, 1f, 0.05f, 20f));
        mat.SetVector("_WaveC", new Vector4(-0.6f, 0.8f, 0.05f, 10f));
        mat.SetFloat("_RippleScale", 0.35f);
        mat.SetFloat("_RippleStrength", 0.4f);
        mat.SetFloat("_RefractionStrength", 0.02f);
        mat.SetFloat("_FoamDistance", 1.2f);
        mat.SetFloat("_FoamNoiseScale", 0.8f);
        mat.SetFloat("_CrestFoam", 0.15f);
        AssetDatabase.CreateAsset(mat, path);
        return mat;
    }

    // ---------------- Helpers ----------------

    static float Fbm(float x, float y, int octaves)
    {
        float sum = 0f, amp = 0.5f, norm = 0f, freq = 1f;
        for (int i = 0; i < octaves; i++)
        {
            sum += amp * Mathf.PerlinNoise(x * freq, y * freq);
            norm += amp;
            amp *= 0.5f;
            freq *= 2f;
        }
        return sum / norm;
    }

    internal static float SmoothStep(float a, float b, float x)
    {
        float t = Mathf.Clamp01((x - a) / (b - a));
        return t * t * (3f - 2f * t);
    }

    internal static void EnsureFolder(string path)
    {
        if (AssetDatabase.IsValidFolder(path)) return;
        string parent = Path.GetDirectoryName(path).Replace('\\', '/');
        EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
    }
}
