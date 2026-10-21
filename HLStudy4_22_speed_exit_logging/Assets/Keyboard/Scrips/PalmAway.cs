using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;


public class PalmAway : MonoBehaviour
{
    public GameObject ForwardKeyboard, ReverseKeyboard;
    public float distancethreshold, ReverseT;
    // Start is called before the first frame update
    void Start()
    {

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

            float distance = Vector3.Magnitude(viewDirection);

            if (distance > distancethreshold)
            {
                //ReverseKeyboard.transform.position = indexPose.Position;
                ForwardKeyboard.SetActive(false);
                ReverseKeyboard.SetActive(true);
            }
            else if (distance < ReverseT)
            {
                ForwardKeyboard.SetActive(true);
                ReverseKeyboard.SetActive(false);
            }

        }


    }
}
