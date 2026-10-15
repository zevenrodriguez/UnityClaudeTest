using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Generates a finely subdivided plane so the water shader's vertex waves have
/// enough vertices to displace. Unity's built-in Plane is too coarse for this.
/// </summary>
[ExecuteAlways]
[RequireComponent(typeof(MeshFilter), typeof(MeshRenderer))]
public class WaterSurface : MonoBehaviour
{
    [Min(1f)] public float size = 50f;
    [Range(2, 1024)] public int resolution = 200;
    [Tooltip("Extra vertical bounds so wave displacement isn't culled.")]
    [Min(0f)] public float boundsPadding = 3f;

    Mesh _mesh;

    void OnEnable() => Rebuild();

    void OnValidate()
    {
        if (isActiveAndEnabled) Rebuild();
    }

    void OnDisable()
    {
        if (_mesh == null) return;
        if (Application.isPlaying) Destroy(_mesh);
        else DestroyImmediate(_mesh);
        _mesh = null;
    }

    public void Rebuild()
    {
        if (_mesh == null)
        {
            _mesh = new Mesh { name = "WaterSurface", hideFlags = HideFlags.DontSave };
            _mesh.indexFormat = IndexFormat.UInt32;
        }

        int verts = resolution + 1;
        var vertices = new Vector3[verts * verts];
        var uvs = new Vector2[vertices.Length];
        var triangles = new int[resolution * resolution * 6];
        float half = size * 0.5f;
        float step = size / resolution;

        for (int z = 0, i = 0; z < verts; z++)
        {
            for (int x = 0; x < verts; x++, i++)
            {
                vertices[i] = new Vector3(x * step - half, 0f, z * step - half);
                uvs[i] = new Vector2((float)x / resolution, (float)z / resolution);
            }
        }

        for (int z = 0, t = 0; z < resolution; z++)
        {
            for (int x = 0; x < resolution; x++, t += 6)
            {
                int i = z * verts + x;
                triangles[t] = i;
                triangles[t + 1] = i + verts;
                triangles[t + 2] = i + 1;
                triangles[t + 3] = i + 1;
                triangles[t + 4] = i + verts;
                triangles[t + 5] = i + verts + 1;
            }
        }

        _mesh.Clear();
        _mesh.vertices = vertices;
        _mesh.uv = uvs;
        _mesh.triangles = triangles;
        _mesh.RecalculateNormals();
        _mesh.bounds = new Bounds(Vector3.zero, new Vector3(size + boundsPadding * 2f, boundsPadding * 2f, size + boundsPadding * 2f));

        GetComponent<MeshFilter>().sharedMesh = _mesh;
    }
}
