using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Events;

public class BloomGesture : MonoBehaviour
{
    public UnityEvent InvertEvent;
    public GameObject ForwardKeyboard, ReverseKeyboard;
    private bool isOpen = false;

    public void Start()
    {
        ForwardKeyboard.SetActive(true);
        ReverseKeyboard.SetActive(false);

    }
    private float flatHandThreshold = 45.0f;
    //手掌向上的法线与摄像头前向射线之间的夹角
    private float facingCameraTrackingThreshold = 80.0f;
    //是否要求手指打开
    public bool requireFlatHand = true;
    public bool IsPalmMeetingThresholdRequirements()
    {
        MixedRealityPose palmPose;
        if (requireFlatHand)
        {
            MixedRealityPose ThumbTipPose, ringTipPose;
            Handedness handedness = Handedness.Right;
           if( HandJointUtils.TryGetJointPose(TrackedHandJoint.ThumbTip, Handedness.Right, out ThumbTipPose)&&
            HandJointUtils.TryGetJointPose(TrackedHandJoint.RingTip, Handedness.Right, out ringTipPose)&&
            HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, Handedness.Right, out palmPose))
            {
                var handNormal = Vector3.Cross(ThumbTipPose.Position - palmPose.Position,
                                 ringTipPose.Position - ThumbTipPose.Position).normalized;
                handNormal *= (handedness == Handedness.Right) ? 1.0f : -1.0f;


                if (Vector3.Angle(palmPose.Up, handNormal) > flatHandThreshold)
                {
                    return false;
                }
            }
        }

        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, Handedness.Right, out palmPose))
        {
            float palmCameraAngle = Vector3.Angle(palmPose.Up, CameraCache.Main.transform.forward);
            return palmCameraAngle < facingCameraTrackingThreshold;
        }
        return false;
    }
    private void Update()
    {
        bool isOpen = IsPalmMeetingThresholdRequirements();
        if (isOpen)
        {
            ForwardKeyboard.SetActive(false);
            ReverseKeyboard.SetActive(true);
        }
        else
        {
            ForwardKeyboard.SetActive(true);
            ReverseKeyboard.SetActive(false);
        }
    }

}