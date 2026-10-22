// Atoll ground for URP: terrain and rocks exported from BlenderTools/atoll_scene.py.
// Vertex color rgb = sand / mud / reef / seagrass tint, alpha = muck amount; uv0.x = wetness.
// Muck areas get dark organic mud with silty specks, puddly sheen and lumpy relief.
Shader "Mangrove/Ground"
{
    Properties
    {
        [Header(Muck)]
        _MudDark ("Mud Dark", Color) = (0.112, 0.093, 0.07, 1)
        _MudMid ("Mud Mid", Color) = (0.206, 0.176, 0.133, 1)
        _MudLight ("Mud Light", Color) = (0.293, 0.248, 0.183, 1)
        _SpeckColor ("Leaf Speck Color", Color) = (0.437, 0.349, 0.235, 1)
        _MuckScale ("Muck Scale", Float) = 1.5

        [Header(Surface)]
        _DrySmoothness ("Dry Smoothness", Range(0, 1)) = 0.08
        _WetSmoothness ("Wet Smoothness", Range(0, 1)) = 0.7
        _PuddleSmoothness ("Puddle Smoothness", Range(0, 1)) = 0.88
        _BumpHeight ("Bump Height (m)", Range(0, 0.1)) = 0.03
    }

    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "MangroveCommon.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _MudDark;
            half4 _MudMid;
            half4 _MudLight;
            half4 _SpeckColor;
            float _MuckScale;
            half _DrySmoothness;
            half _WetSmoothness;
            half _PuddleSmoothness;
            float _BumpHeight;
        CBUFFER_END
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }

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
                float2 uv         : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                half4  color      : TEXCOORD2; // rgb linear tint, a = muck
                half   wet        : TEXCOORD3;
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
                output.color = half4(MgToLinear(input.color.rgb), input.color.a);
                output.wet = input.uv.x;
                output.fogFactor = ComputeFogFactor(output.positionCS.z);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                float3 p = input.positionWS;
                half muck = saturate(input.color.a);

                // dark organic mud with silty streaks and specks of broken-down leaves
                float n = MgFbm(p * _MuckScale, 5);
                half3 mud = lerp(lerp(_MudDark.rgb, _MudMid.rgb, smoothstep(0.3, 0.55, n)), _MudLight.rgb, smoothstep(0.55, 0.75, n));
                mud = lerp(mud, _SpeckColor.rgb, 1 - smoothstep(0.12, 0.2, MgCells(p * 22.0)));
                half3 albedo = lerp(input.color.rgb, mud, muck);

                // wet sand / mud is glossier; muck gets puddly patches
                half smoothness = lerp(_DrySmoothness, _WetSmoothness, saturate(input.wet));
                half puddle = lerp(0.35, _PuddleSmoothness, smoothstep(0.45, 0.6, MgNoise(p * 4.0)));
                smoothness = lerp(smoothness, puddle, muck);

                float height = lerp(MgNoise(p * 45.0) * 0.1, MgFbm(p * 3.0, 3), muck) * _BumpHeight;
                float3 N = MgBumpNormal(normalize(input.normalWS), p, height);
                return half4(MgLightPBR(p, N, albedo, smoothness, input.positionCS, input.fogFactor), 1);
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

            HLSLPROGRAM
            #pragma vertex MgDepthVert
            #pragma fragment MgNullFrag
            #pragma multi_compile_instancing
            ENDHLSL
        }
    }

    FallBack Off
}
