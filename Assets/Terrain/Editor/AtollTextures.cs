using System;
using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Procedurally generates tileable albedo + normal maps and TerrainLayers for the atoll.
/// Existing layers/textures are reused, so you can swap in photo-scanned textures
/// (e.g. from Poly Haven) by replacing the PNGs or editing the .terrainlayer assets.
/// </summary>
static class AtollTextures
{
    const int Size = 512;

    struct LayerSpec
    {
        public string name;
        public float tileSize;
        public float smoothness;
        public float normalStrength;
        public Func<float, float, int, int, (Color albedo, float height)> sample;
    }

    public static TerrainLayer[] GetOrCreateLayers(string folder)
    {
        var specs = new[]
        {
            new LayerSpec { name = "Sand", tileSize = 6f, smoothness = 0.05f, normalStrength = 2f, sample = Sand },
            new LayerSpec { name = "Seafloor", tileSize = 8f, smoothness = 0.2f, normalStrength = 3f, sample = Seafloor },
            new LayerSpec { name = "Vegetation", tileSize = 5f, smoothness = 0.1f, normalStrength = 3f, sample = Vegetation },
            new LayerSpec { name = "Reef", tileSize = 8f, smoothness = 0.15f, normalStrength = 5f, sample = Reef },
        };

        var layers = new TerrainLayer[specs.Length];
        for (int i = 0; i < specs.Length; i++)
            layers[i] = GetOrCreateLayer(folder, specs[i]);
        return layers;
    }

    static TerrainLayer GetOrCreateLayer(string folder, LayerSpec spec)
    {
        string layerPath = $"{folder}/{spec.name}.terrainlayer";
        var layer = AssetDatabase.LoadAssetAtPath<TerrainLayer>(layerPath);
        if (layer != null) return layer;

        string albedoPath = $"{folder}/{spec.name}_Albedo.png";
        string normalPath = $"{folder}/{spec.name}_Normal.png";
        if (!File.Exists(albedoPath) || !File.Exists(normalPath))
            WriteTextures(spec, albedoPath, normalPath);

        layer = new TerrainLayer
        {
            diffuseTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(albedoPath),
            normalMapTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(normalPath),
            tileSize = new Vector2(spec.tileSize, spec.tileSize),
            smoothness = spec.smoothness,
            metallic = 0f,
        };
        AssetDatabase.CreateAsset(layer, layerPath);
        return layer;
    }

    static void WriteTextures(LayerSpec spec, string albedoPath, string normalPath)
    {
        var albedo = new Color[Size * Size];
        var height = new float[Size * Size];
        for (int y = 0; y < Size; y++)
        {
            for (int x = 0; x < Size; x++)
            {
                var (c, h) = spec.sample(x / (float)Size, y / (float)Size, x, y);
                c.a = 1f;
                albedo[y * Size + x] = c;
                height[y * Size + x] = h;
            }
        }

        var normals = new Color[Size * Size];
        for (int y = 0; y < Size; y++)
        {
            for (int x = 0; x < Size; x++)
            {
                float dx = height[y * Size + (x + 1) % Size] - height[y * Size + (x - 1 + Size) % Size];
                float dy = height[((y + 1) % Size) * Size + x] - height[((y - 1 + Size) % Size) * Size + x];
                var n = new Vector3(-dx * spec.normalStrength, -dy * spec.normalStrength, 1f).normalized;
                normals[y * Size + x] = new Color(n.x * 0.5f + 0.5f, n.y * 0.5f + 0.5f, n.z * 0.5f + 0.5f, 1f);
            }
        }

        SavePng(albedo, albedoPath, false);
        SavePng(normals, normalPath, true);
    }

    static void SavePng(Color[] pixels, string path, bool isNormal)
    {
        var tex = new Texture2D(Size, Size, TextureFormat.RGBA32, false, isNormal);
        tex.SetPixels(pixels);
        tex.Apply();
        File.WriteAllBytes(path, tex.EncodeToPNG());
        UnityEngine.Object.DestroyImmediate(tex);

        AssetDatabase.ImportAsset(path);
        var importer = (TextureImporter)AssetImporter.GetAtPath(path);
        importer.textureType = isNormal ? TextureImporterType.NormalMap : TextureImporterType.Default;
        importer.sRGBTexture = !isNormal;
        importer.wrapMode = TextureWrapMode.Repeat;
        importer.anisoLevel = 4;
        importer.SaveAndReimport();
    }

    // ---------------- Materials ----------------

    // Coral sand: pale and fine-grained, with occasional shell fragments.
    static (Color, float) Sand(float u, float v, int px, int py)
    {
        float g = TileFbm(u, v, 8, 5, 1);
        float grain = ValueNoise(u * 256f, v * 256f, 256, 7);
        var c = Color.Lerp(new Color(0.80f, 0.74f, 0.60f), new Color(0.94f, 0.90f, 0.80f), g) * (0.9f + 0.2f * grain);
        if (Hash(px, py, 11) > 0.993f) c *= 0.72f;
        return (c, g * 0.4f + grain * 0.6f);
    }

    // Wet, wave-rippled sand for the lagoon and ocean floor.
    static (Color, float) Seafloor(float u, float v, int px, int py)
    {
        float w = TileFbm(u, v, 4, 3, 21);
        float g = TileFbm(u, v, 16, 3, 23);
        float ripple = 0.5f + 0.5f * Mathf.Sin((u * 14f + v * 2f + w * 1.5f) * Mathf.PI * 2f);
        float grain = ValueNoise(u * 256f, v * 256f, 256, 25);
        var c = Color.Lerp(new Color(0.60f, 0.57f, 0.46f), new Color(0.80f, 0.76f, 0.64f), 0.6f * ripple + 0.4f * g) * (0.92f + 0.16f * grain);
        return (c, ripple * 0.7f + grain * 0.3f);
    }

    // Low tropical scrub and grass, with sun-dried patches.
    static (Color, float) Vegetation(float u, float v, int px, int py)
    {
        float patches = TileFbm(u, v, 4, 4, 41);
        float blades = TileFbm(u, v, 64, 2, 43);
        float clumps = TileFbm(u, v, 16, 3, 45);
        var green = Color.Lerp(new Color(0.14f, 0.24f, 0.07f), new Color(0.30f, 0.42f, 0.13f), blades * 0.6f + clumps * 0.4f);
        var c = Color.Lerp(green, new Color(0.55f, 0.50f, 0.30f), AtollGenerator.SmoothStep(0.55f, 0.8f, patches));
        return (c, blades * 0.6f + clumps * 0.4f);
    }

    // Coral rubble / reef rock with patches of algae.
    static (Color, float) Reef(float u, float v, int px, int py)
    {
        float r = 1f - Mathf.Abs(TileFbm(u, v, 6, 5, 61) * 2f - 1f);
        float detail = TileFbm(u, v, 32, 3, 63);
        float algae = AtollGenerator.SmoothStep(0.55f, 0.7f, TileFbm(u, v, 4, 3, 65));
        var c = Color.Lerp(new Color(0.36f, 0.33f, 0.27f), new Color(0.70f, 0.65f, 0.56f), r);
        c = Color.Lerp(c, new Color(0.30f, 0.35f, 0.20f), algae * 0.6f) * (0.85f + 0.3f * detail);
        return (c, r * 0.7f + detail * 0.3f);
    }

    // ---------------- Tileable noise ----------------

    static float Hash(int x, int y, int seed)
    {
        unchecked
        {
            uint h = (uint)(x * 374761393 + y * 668265263 + seed * 982451653);
            h = (h ^ (h >> 13)) * 1274126177u;
            h ^= h >> 16;
            return (h & 0xFFFFFF) / 16777215f;
        }
    }

    static int Wrap(int i, int period) => ((i % period) + period) % period;

    static float ValueNoise(float x, float y, int period, int seed)
    {
        int x0 = Mathf.FloorToInt(x), y0 = Mathf.FloorToInt(y);
        float fx = x - x0, fy = y - y0;
        float u = fx * fx * (3f - 2f * fx), v = fy * fy * (3f - 2f * fy);
        int xa = Wrap(x0, period), xb = Wrap(x0 + 1, period);
        int ya = Wrap(y0, period), yb = Wrap(y0 + 1, period);
        return Mathf.Lerp(
            Mathf.Lerp(Hash(xa, ya, seed), Hash(xb, ya, seed), u),
            Mathf.Lerp(Hash(xa, yb, seed), Hash(xb, yb, seed), u), v);
    }

    static float TileFbm(float u, float v, int period, int octaves, int seed)
    {
        float sum = 0f, amp = 0.5f, norm = 0f;
        for (int i = 0; i < octaves; i++)
        {
            sum += amp * ValueNoise(u * period, v * period, period, seed + i * 31);
            norm += amp;
            amp *= 0.5f;
            period *= 2;
        }
        return sum / norm;
    }
}
