Shader "Custom/Opacity Mask" {
    Properties{
        _MainTex("Texture", 2D) = "white" {}
        _OpacityMask("Opacity Mask", 2D) = "white" {}
    }

        SubShader{
            Tags {"Queue" = "Transparent" "RenderType" = "Opaque" }
            LOD 200

            Pass {
                CGPROGRAM
                #pragma vertex vert
                #pragma fragment frag
                #include "UnityCG.cginc"

                struct appdata {
                    float4 vertex : POSITION;
                    float2 uv : TEXCOORD0;
                };

                struct v2f {
                    float2 uv : TEXCOORD0;
                    float4 vertex : SV_POSITION;
                };

                sampler2D _MainTex;
                sampler2D _OpacityMask;

                v2f vert(appdata v) {
                    v2f o;
                    o.vertex = UnityObjectToClipPos(v.vertex);
                    o.uv = v.uv;
                    return o;
                }

                fixed4 frag(v2f i) : SV_Target {
                    // Sample the main texture
                    fixed4 col = tex2D(_MainTex, i.uv);

                // Use the opacity mask to mask out parts of the texture
                col.a *= tex2D(_OpacityMask, i.uv).r;

                // Output the color with opacity mask applied
                return col;
            }
            ENDCG
        }
    }
        FallBack "Diffuse"
}
