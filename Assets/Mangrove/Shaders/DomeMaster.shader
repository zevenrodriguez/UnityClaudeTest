// Stitches five 90° camera faces (a half cube around the dome) into an equidistant fisheye
// "domemaster" image: center = dome zenith, edge = _HalfFov from it, top of image = back of the dome.
// Used by DomeMasterCamera via Graphics.Blit.
Shader "Hidden/Mangrove/DomeMaster"
{
    Properties
    {
        _MainTex ("Unused", 2D) = "black" {}
    }

    SubShader
    {
        Cull Off ZWrite Off ZTest Always

        Pass
        {
            CGPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _Face0, _Face1, _Face2, _Face3, _Face4;
            float4 _FaceRight[5];
            float4 _FaceUp[5];
            float4 _FaceForward[5];
            float4 _DomeRight;
            float4 _DomeUp;
            float4 _DomeForward;
            float _HalfFov; // radians

            float4 SampleFace(int face, float2 uv)
            {
                float4 coord = float4(uv, 0, 0);
                if (face == 0) return tex2Dlod(_Face0, coord);
                if (face == 1) return tex2Dlod(_Face1, coord);
                if (face == 2) return tex2Dlod(_Face2, coord);
                if (face == 3) return tex2Dlod(_Face3, coord);
                return tex2Dlod(_Face4, coord);
            }

            float4 frag(v2f_img i) : SV_Target
            {
                float2 p = i.uv * 2.0 - 1.0;
                float r = length(p);
                if (r > 1.0) return float4(0, 0, 0, 1);

                // equidistant fisheye: angle from the zenith grows linearly with radius
                float theta = r * _HalfFov;
                float phi = atan2(p.y, p.x);
                float3 dir = normalize(_DomeForward.xyz * cos(theta)
                                     + (_DomeRight.xyz * cos(phi) + _DomeUp.xyz * sin(phi)) * sin(theta));

                int face = 0;
                float best = -2;
                [unroll] for (int k = 0; k < 5; k++)
                {
                    float d = dot(dir, _FaceForward[k].xyz);
                    if (d > best) { best = d; face = k; }
                }

                float2 uv = float2(dot(dir, _FaceRight[face].xyz), dot(dir, _FaceUp[face].xyz)) / best * 0.5 + 0.5;
                return float4(SampleFace(face, uv).rgb, 1);
            }
            ENDCG
        }
    }
}
