using UnityEditor;
using UnityEngine;

static class WaterSetup
{
    const string MaterialPath = "Assets/Water/Materials/Water.mat";

    [MenuItem("GameObject/3D Object/Water Surface", false, 10)]
    [MenuItem("Tools/Water/Create Water Surface")]
    static void CreateWater(MenuCommand command)
    {
        var go = new GameObject("Water", typeof(MeshFilter), typeof(MeshRenderer), typeof(WaterSurface));
        var renderer = go.GetComponent<MeshRenderer>();
        renderer.sharedMaterial = GetOrCreateMaterial();
        renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;

        GameObjectUtility.SetParentAndAlign(go, command.context as GameObject);
        Undo.RegisterCreatedObjectUndo(go, "Create Water Surface");
        Selection.activeObject = go;
    }

    static Material GetOrCreateMaterial()
    {
        var material = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath);
        if (material != null) return material;

        var shader = Shader.Find("Custom/Water");
        if (shader == null)
        {
            Debug.LogError("Water shader 'Custom/Water' not found.");
            return null;
        }

        if (!AssetDatabase.IsValidFolder("Assets/Water/Materials"))
            AssetDatabase.CreateFolder("Assets/Water", "Materials");

        material = new Material(shader) { name = "Water" };
        AssetDatabase.CreateAsset(material, MaterialPath);
        AssetDatabase.SaveAssets();
        return material;
    }
}
