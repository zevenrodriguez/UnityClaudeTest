using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

static class NightSkySetup
{
    const string MaterialPath = "Assets/Sky/Materials/NightSky.mat";

    /// <summary>
    /// Assigns the night sky skybox, turns the main directional light into moonlight
    /// (the moon in the sky follows it), and sets a dim blue ambient.
    /// </summary>
    [MenuItem("Tools/Sky/Apply Night Sky")]
    static void Apply()
    {
        var material = GetOrCreateMaterial();
        if (material == null) return;

        RenderSettings.skybox = material;
        RenderSettings.ambientMode = AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.06f, 0.08f, 0.14f);
        RenderSettings.ambientEquatorColor = new Color(0.035f, 0.045f, 0.07f);
        RenderSettings.ambientGroundColor = new Color(0.01f, 0.012f, 0.02f);

        var light = FindMainLight();
        if (light != null)
        {
            Undo.RecordObjects(new Object[] { light, light.transform }, "Apply Night Sky");
            light.transform.rotation = Quaternion.Euler(32f, -140f, 0f); // moon 32° above the horizon
            light.useColorTemperature = false;
            light.color = new Color(0.64f, 0.74f, 1f);
            light.intensity = 0.3f;
            RenderSettings.sun = light;
        }
        else
        {
            Debug.LogWarning("No directional light found; the moon will use the material's Moon Direction.");
            material.SetFloat("_MoonFollowsLight", 0f);
        }

        DynamicGI.UpdateEnvironment();
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        Selection.activeObject = material;
    }

    static Material GetOrCreateMaterial()
    {
        var material = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath);
        if (material != null) return material;

        var shader = Shader.Find("Custom/NightSky");
        if (shader == null)
        {
            Debug.LogError("Shader 'Custom/NightSky' not found.");
            return null;
        }

        if (!AssetDatabase.IsValidFolder("Assets/Sky/Materials"))
            AssetDatabase.CreateFolder("Assets/Sky", "Materials");

        material = new Material(shader) { name = "NightSky" };
        AssetDatabase.CreateAsset(material, MaterialPath);
        AssetDatabase.SaveAssets();
        return material;
    }

    static Light FindMainLight()
    {
        if (RenderSettings.sun != null) return RenderSettings.sun;
        foreach (var light in Object.FindObjectsByType<Light>())
        {
            if (light.type == LightType.Directional) return light;
        }
        return null;
    }
}
