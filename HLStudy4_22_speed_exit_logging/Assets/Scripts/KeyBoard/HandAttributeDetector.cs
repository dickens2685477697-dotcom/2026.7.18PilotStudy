using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.XR.Interaction.Toolkit.AffordanceSystem.Receiver.Primitives;

public class HandAttributeDetector : MonoBehaviour
{
    public GameObject Keyboard;
    // This angle is in relation with the camera view angle. 
    [Header("Rotation")]
    public float WristRotateAngle;

    [Header("Distance - In relation to keyboard.")]
    public float PalmToKeyboardDistance;
    public float CameraToPalmDistance;

    [Header("Pinch Detection")]
    public float IndexToThumbDistance;
    public bool ifPinched = false;
    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        Handedness handedness = Handedness.Right;
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, handedness, out MixedRealityPose palmPose) &&
            HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, handedness, out MixedRealityPose indexPose))
        {
            DetectRotation(palmPose);
            DetectCameraToPalmDistance(palmPose);
            DetectPalmToKeyboardDistance(palmPose);
            PinchDetection(indexPose);
        }
    }

    /// <summary>
    /// Detect Rotation of hand relative to camera.
    /// </summary>
    /// <param name="palm"></param>
    void DetectRotation(MixedRealityPose palm)
    {
        // Check if the hand is facing the user
        Vector3 palmNormal = palm.Up;
        Vector3 viewDirection = CameraCache.Main.transform.position - palm.Position;

        WristRotateAngle = Vector3.Angle(palmNormal, viewDirection);
    }

    /// <summary>
    /// Detect Distance of hand from Camera to palm
    /// </summary>
    /// <param name="palm"></param>
    void DetectCameraToPalmDistance(MixedRealityPose palm)
    {
        CameraToPalmDistance = Vector3.Distance(palm.Position, CameraCache.Main.transform.position);
    }

    /// <summary>
    /// Detect Distance of hand from Keyboard to Palm, note that it is relative to the plane of keyboard instead of the center point.
    /// </summary>
    /// <param name="palm"></param>
    void DetectPalmToKeyboardDistance(MixedRealityPose palm)
    {
        Vector3 planeNormal = Keyboard.transform.up;
        Vector3 planePoint = Keyboard.transform.position;

        PalmToKeyboardDistance = Vector3.Dot(planeNormal, (palm.Position - planePoint));
    }

    void PinchDetection(MixedRealityPose IndexTip)
    {
        Handedness handedness = Handedness.Right;
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.ThumbTip, handedness, out MixedRealityPose thumbTip))
        {
            IndexToThumbDistance = Vector3.Distance(thumbTip.Position, IndexTip.Position);
            if (IndexToThumbDistance < 0.01)
            {
                ifPinched = true;
            }
            else if (IndexToThumbDistance > 0.01)
            {
                ifPinched = false;
            }
        }
    }
}
