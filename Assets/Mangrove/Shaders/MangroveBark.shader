// Red mangrove bark for URP, matching BlenderTools/mangrove_bark.py.
// Base tint comes from the Blender vertex colors (tide line, lichen, mud); this adds
// lengthwise fissures, lenticels, lichen crust, tide-band algae and barnacles, and wet bark at the base.
// Works in object space, where y = height above the tree's ground.
Shader "Mangrove/Bark"
{
    Properties
    {
        _Tint ("Tint", Color) = (1, 1, 1, 1)

        [Header(Fissures)]
        _FissureScale ("Fissure Scale (across, along)", Vector) = (14, 2.2, 0, 0)
        _FissureDepth ("Fissure Depth", Range(0, 1)) = 0.45
        _InnerBarkColor ("Inner Bark Color", Color) = (0.349, 0.206, 0.143, 1)

        [Header(Lenticels and Lichen)]
        _LenticelColor ("Lenticel Color", Color) = (0.601, 0.566, 0.506, 1)
        _LenticelDensity ("Lenticel Density", Float) = 55
        _LichenColorA ("Lichen Color A", Color) = (0.547, 0.566, 0.485, 1)
        _LichenColorB ("Lichen Color B", Color) = (0.68, 0.68, 0.642, 1)
        _LichenAmount ("Lichen Amount", Range(0, 1)) = 0.8

        [Header(Tide Line)]
        _TideBand ("Tide Band (bottom, top)", Vector) = (0.05, 0.55, 0, 0)
        _AlgaeColor ("Algae Color", Color) = (0.206, 0.248, 0.143, 1)
        _BarnacleColor ("Barnacle Color", Color) = (0.735, 0.715, 0.665, 1)
        _WetHeight ("Wet Height", Float) = 0.45
        _MudColor ("Mud Color", Color) = (0.19, 0.16, 0.128, 1)

        [Header(Surface)]
        _Smoothness ("Dry Smoothness", Range(0, 1)) = 0.18
        _WetSmoothness ("Wet Smoothness", Range(0, 1)) = 0.72
        _BumpHeight ("Bump Height (m)", Range(0, 0.02)) = 0.004
    }

    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "MangroveCommon.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _Tint;
            float4 _FissureScale;
            half _FissureDepth;
            half4 _InnerBarkColor;
            half4 _LenticelColor;
            float _LenticelDensity;
            half4 _LichenColorA;
            half4 _LichenColorB;
            half _LichenAmount;
            float4 _TideBand;
            half4 _AlgaeColor;
            half4 _BarnacleColor;
            float _WetHeight;
            half4 _MudColor;
            half _Smoothness;
            half _WetSmoothness;
            float _BumpHeight;
        CBUFFER_END
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Cull Off

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                half4  color      : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float3 positionOS : TEXCOORD2;
                half3  color      : TEXCOORD3;
                half   fogFactor  : TEXCOORD4;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            Varyings Vert(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformWorldToHClip(output.positionWS);
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.positionOS = input.positionOS.xyz;
                output.color = MgToLinear(input.color.rgb);
                output.fogFactor = ComputeFogFactor(output.positionCS.z);
                return output;
            }

            half4 Frag(Varyings input, bool isFrontFace : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                float3 p = input.positionOS;
                half3 base = input.color * _Tint.rgb;

                // fissured bark: noise stretched along the stem
                float fis = MgFbm(float3(p.x * _FissureScale.x, p.y * _FissureScale.y, p.z * _FissureScale.x), 4);
                half ridge = smoothstep(0.38, 0.55, fis);
                base *= lerp(0.55, 1.15, ridge);
                base = lerp(base, _InnerBarkColor.rgb, (1 - ridge) * _FissureDepth);
                base *= lerp(0.8, 1.15, smoothstep(0.3, 0.7, MgNoise(p * 0.8)));

                // lenticels: small pale breathing pores
                half len = 1 - smoothstep(0.06, 0.1, MgCells(p * _LenticelDensity));
                base = lerp(base, _LenticelColor.rgb, len * 0.55);

                // lichen crust on the drier bark higher up
                half dry = smoothstep(0.4, 0.9, p.y);
                half lichen = smoothstep(0.55, 0.63, MgFbm(p * 4.0, 3)) * dry * _LichenAmount;
                base = lerp(base, lerp(_LichenColorA.rgb, _LichenColorB.rgb, MgNoise(p * 12.0)), lichen);

                // tide band: algae slime and barnacle clusters
                half tide = smoothstep(_TideBand.x, _TideBand.x + 0.15, p.y) * (1 - smoothstep(_TideBand.y - 0.2, _TideBand.y, p.y));
                base = lerp(base, _AlgaeColor.rgb, tide * 0.55);
                half barnacle = (1 - smoothstep(0.12, 0.2, MgCells(p * 70.0))) * smoothstep(0.45, 0.6, MgNoise(p * 3.0)) * tide;
                base = lerp(base, _BarnacleColor.rgb, barnacle);

                // wet mud at the base
                half wet = 1 - smoothstep(0.1, _WetHeight, p.y);
                base = lerp(base, _MudColor.rgb, wet * 0.6);

                half smoothness = lerp(_Smoothness, _WetSmoothness, wet) * (1 - lichen * 0.8);
                float height = (ridge * 0.6 + len * 0.2 + barnacle * 0.8) * _BumpHeight;

                float3 N = normalize(input.normalWS) * (isFrontFace ? 1 : -1);
                N = MgBumpNormal(N, input.positionWS, height);
                return half4(MgLightPBR(input.positionWS, N, base, smoothness, input.positionCS, input.fogFactor), 1);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull Off

            HLSLPROGRAM
            #pragma vertex MgShadowVert
            #pragma fragment MgNullFrag
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #pragma multi_compile_instancing
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull Off

            HLSLPROGRAM
            #pragma vertex MgDepthVert
            #pragma fragment MgNullFrag
            #pragma multi_compile_instancing
            ENDHLSL
        }
    }

    FallBack Off
}
