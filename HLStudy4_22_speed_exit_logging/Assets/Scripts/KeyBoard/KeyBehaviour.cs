using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Microsoft.MixedReality.Toolkit.Input;
using JetBrains.Annotations;
using Microsoft.MixedReality.Toolkit.Utilities;
using Microsoft.MixedReality.Toolkit;

public class KeyBehaviour : MonoBehaviour
{
    // Public Object assign to plane object and store InEvent.
    public bool InEvent;
    public Material inMaterial, outMaterial, execute010TriggerMaterial;
    public Transform planeTransform;
    Bounds bounds;

    private GameObject execute010Trigger;

    // Start is called before the first frame update

    void Start()
    {
        execute010Trigger = GameObject.Find("Execute010Trigger");
        execute010Trigger.SetActive(false);
    }

    // Update is called once per frame
    void Update()
    {
        CheckFingerCrossedPlane(Handedness.Left);
        CheckFingerCrossedPlane(Handedness.Right);
    }

    private void CheckFingerCrossedPlane(Handedness handedness)
    {
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, handedness, out MixedRealityPose fingerTipPose) && 
            (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexDistalJoint, handedness, out MixedRealityPose fingerDistalPose)))
        {
            Vector3 fingerTiptoPlane = planeTransform.position - fingerTipPose.Position;
            float dotProduct = Vector3.Dot(fingerTipPose.Up, fingerTiptoPlane);
            print(dotProduct);

            if (dotProduct > 0.0f && IsWithinPlaneBounds(fingerTipPose.Position))
            {
                InEvent = true;
                execute010Trigger.SetActive(true);
            }
            else
            {
                InEvent = false;
            }
        }
    }

    private bool IsWithinPlaneBounds(Vector3 point)
    {
        Vector3 localPoint = planeTransform.InverseTransformPoint(point);

        if (Mathf.Abs(localPoint.x) <= planeTransform.localScale.x/2 &&
            Mathf.Abs(localPoint.z) <= planeTransform.localScale.z/2)
        {
            return true;
        }
        return false;
    }
}
