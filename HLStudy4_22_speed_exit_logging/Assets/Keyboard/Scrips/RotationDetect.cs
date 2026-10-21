using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class RotationDetect : MonoBehaviour
{
    public GameObject ForwardKeyboard, ReverseKeyboard, KeyboardPlane;
    public float WristRotateAngle;
    // Start is called before the first frame update
    void Start()
    {
        KeyboardPlane.SetActive(true);
        ForwardKeyboard.SetActive(true);
        ReverseKeyboard.SetActive(false);
    }

    // Update is called once per frame
    void Update()
    {
        Handedness handedness = Handedness.Right;
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, handedness, out MixedRealityPose palmPose) &&
            HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, handedness, out MixedRealityPose indexPose))
        {
            // Check if the hand is facing the user
            Vector3 palmNormal = palmPose.Up;
            Vector3 viewDirection = CameraCache.Main.transform.position - palmPose.Position;

            WristRotateAngle = Vector3.Angle(palmNormal, viewDirection);

            print(WristRotateAngle);

            if (WristRotateAngle > 100.0f)
            {
                KeyboardPlane.SetActive(false);
                ForwardKeyboard.SetActive(false);
                ReverseKeyboard.SetActive(true);
            }
            else
            {
                KeyboardPlane.SetActive(true);
                ForwardKeyboard.SetActive(true);
                ReverseKeyboard.SetActive(false);
            }

        }
   
      
    }

}
