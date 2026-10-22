using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Import settings for the Blender exports in Assets/Mangrove/Models: keeps Blender's normals and
/// vertex colors, skips cameras/lights/animation, assigns the mangrove materials, and builds a
/// LOD Group from meshes named *_LOD0, *_LOD1, *_LOD2.
/// </summary>
class MangroveModelPostprocessor : AssetPostprocessor
{
    // Screen height below which each LOD hands over to the next; the last one culls tiny trees.
    static readonly float[] LodHeights = { 0.2f, 0.06f, 0.008f };
    static readonly Regex LodSuffix = new Regex(@"_LOD(\d+)$");

    bool IsMangroveModel => assetPath.StartsWith(MangroveAssets.ModelFolder + "/");

    void OnPreprocessModel()
    {
        if (!IsMangroveModel) return;
        var importer = (ModelImporter)assetImporter;
        importer.importCameras = false;
        importer.importLights = false;
        importer.importVisibility = false;
        importer.importBlendShapes = false;
        importer.importAnimation = false;
        importer.animationType = ModelImporterAnimationType.None;
        importer.importNormals = ModelImporterNormals.Import;
        importer.meshCompression = ModelImporterMeshCompression.Off;
        importer.isReadable = false;
        importer.generateSecondaryUV = false;
        importer.indexFormat = ModelImporterIndexFormat.Auto;
        importer.materialImportMode = ModelImporterMaterialImportMode.None;
    }

    void OnPostprocessModel(GameObject root)
    {
        if (!IsMangroveModel) return;

        foreach (var renderer in root.GetComponentsInChildren<MeshRenderer>(true))
        {
            var filter = renderer.GetComponent<MeshFilter>();
            if (filter == null || filter.sharedMesh == null) continue;
            var mesh = filter.sharedMesh;
            var materials = new Material[mesh.subMeshCount];
            for (int i = 0; i < materials.Length; i++)
                materials[i] = LoadMaterial(MaterialPathFor(renderer.name, i));
            renderer.sharedMaterials = materials;
        }

        SetupLods(root);
    }

    static string MaterialPathFor(string objectName, int submesh)
    {
        switch (objectName)
        {
            case "Atoll_Terrain":
            case "Atoll_Rocks":
                return MangroveAssets.GroundMaterial;
            case "Atoll_LeafLitter":
            case "Atoll_Debris":
                return MangroveAssets.LitterMaterial;
            default: // tree LODs: submesh 0 = bark, 1 = leaves
                return submesh == 0 ? MangroveAssets.BarkMaterial : MangroveAssets.FoliageMaterial;
        }
    }

    Material LoadMaterial(string path)
    {
        context.DependsOnSourceAsset(path);
        return AssetDatabase.LoadAssetAtPath<Material>(path);
    }

    static void SetupLods(GameObject root)
    {
        var levels = new SortedDictionary<int, List<Renderer>>();
        foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
        {
            var match = LodSuffix.Match(renderer.name);
            if (!match.Success) continue;
            int level = int.Parse(match.Groups[1].Value);
            if (!levels.TryGetValue(level, out var list)) levels[level] = list = new List<Renderer>();
            list.Add(renderer);
        }
        if (levels.Count < 2) return;

        var group = root.GetComponent<LODGroup>() ?? root.AddComponent<LODGroup>();
        var lods = levels.Values.Select((renderers, i) =>
            new LOD(LodHeights[Mathf.Min(i, LodHeights.Length - 1)], renderers.ToArray())).ToArray();
        group.SetLODs(lods);
        group.RecalculateBounds();
    }
}
