using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.UI;
using static UnityEngine.UI.CanvasScaler;
using Microsoft.MixedReality.Toolkit.Utilities;
using System.Security.AccessControl;
using UnityEngine.Events;
using UnityEngine.EventSystems;
using TMPro;
using System.Diagnostics;
using UnityEditor;
using UnityEngine.Rendering;
using Microsoft.MixedReality.Toolkit;
using Facebook.WitAi.Utilities;
using UnityEngine.UIElements;

public class TriggerPlane : MonoBehaviour
{
    public AcceStimulate Acce;
    public bool InEventTriggered = false, HesEventTriggered = false, OutEventTriggered = false;

    List<GameObject> ButtonGameObjects = new List<GameObject>();

    public bool init, crossed;

    public UnityEvent<string> ExitEvent, EnterEvent;

    public GameObject triggeringPlane;
    public Vector3 triggeringPlaneCenter;
    public Collider triggeringPlaneCollider;
    public Bounds triggerPlaneBound;

    private IMixedRealityHandJointService handJointService;

    public GameObject KeyboardParent; 
    public Collider[] CollidersInChildrenComponents;

    public Handedness handedness = Handedness.Any;
    public MixedRealityPose FingerTipPreviousPos;
    public MixedRealityPose FingerTipCurrentPos;
    public Vector3 FingerTipPreviousCoordinate;
    public Vector3 FingerTipCurrentCoordinate;
    public float FingerTipPreviousZ;
    public float FingerTipCurrentZ;
 
    // Start is called before the first frame update
    void Start()
    {
        InEventTriggered = false;
        crossed = false;
        init = true;
        // Get handjoint service
        CollidersInChildrenComponents = KeyboardParent.GetComponentsInChildren<Collider>();
        //setColliderActive(false);

        triggeringPlane = gameObject;
        triggeringPlaneCollider = gameObject.GetComponent<Collider>();
        Transform triggeringPlaneTransform = gameObject.GetComponent<Transform>();
        triggeringPlaneCenter = triggeringPlaneTransform.localPosition;
        triggerPlaneBound = triggeringPlaneCollider.bounds;

        // Use an lambda function to monitor if InEvent is triggered.
        Acce.InEvent.AddListener(() =>
        {
            InEventTriggered = true;
        });

        Acce.HesEvent.AddListener(() =>
        {
            HesEventTriggered = true;
        });

        Acce.OutEvent.AddListener(() =>
        {
            OutEventTriggered = true;
        });
    }

    // Update is called once per frame
    void FixedUpdate()
    {


        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, Handedness.Any, out FingerTipCurrentPos)) 
        {
            if (init)
            {
                init = false;
                FingerTipPreviousPos = FingerTipCurrentPos;
                return;
            }

            Vector3 FingertipPreviousConv = MatrixConversion(FingerTipPreviousPos);
            Vector3 FingertipCurrentConv = MatrixConversion(FingerTipCurrentPos);
            FingerTipPreviousZ = FingertipPreviousConv.z;
            FingerTipCurrentZ = FingertipCurrentConv.z;
            
            if(FingerTipCurrentZ != FingerTipPreviousZ)
            {
                EnterCrossPlaneChecker(FingerTipCurrentZ, FingerTipPreviousZ);
                ExitCrossPlaneChecker(FingerTipCurrentZ, FingerTipPreviousZ);
                if (crossed == true)
                {
                    // print("Crossed");
                    //setColliderActive(true);

                    if(InEventTriggered)
                    {
                        InEventTriggered = false;
                        crossed = false;
                    }
                    if (HesEventTriggered)
                    {
                        HesEventTriggered = false;
                        //setColliderActive(false);
                    }
                }
            }

            /// Replace Iteration for current frame for the next iteration.
            /// Make sure any functions should be written before this.
            /// Or Two frames will be the same.
            FingerTipPreviousPos = FingerTipCurrentPos;

        }
    }

    /// <summary>
    /// Check if finger has crossed the plane, with the normalised numbers, the finger crossed the plane when it
    /// changes from -0.9 to 0.9. So only when current frame is bigger than previous frame, the plane can be considered 
    /// crossed. 
    /// </summary>
    /// <param name="CurrentFramePos"> The position of current frame </param>
    /// <param name="PreviousFramePos"> The position of previous frame </param>
    /// <returns></returns>
    public void EnterCrossPlaneChecker(float CurrentFramePos, float PreviousFramePos)
    {
        if (CurrentFramePos > 0 && CurrentFramePos > PreviousFramePos && PreviousFramePos < 0)
        {

            print("Enter");
            EnterEvent.Invoke(null);
        }
    }

    public void ExitCrossPlaneChecker(float CurrentFramePos, float PreviousFramePos)
    {
        if (CurrentFramePos < 0 && CurrentFramePos < PreviousFramePos && PreviousFramePos > 0)
        {
            print("Exit");
            ExitEvent.Invoke(null);
        }
    }

    /// <summary>
    /// This is used to turn on and off all colliders with one statement. 
    /// </summary>
    /// <param name="enabledState"> Input a bool value to turn on or off the colliders. </param>
    //public void setColliderActive(bool enabledState = false)
    //{
    //    foreach (Collider collider in CollidersInChildrenComponents)
    //    {
    //        GameObject ButtonObject = collider.gameObject;
    //        ButtonGameObjects.Add(ButtonObject);
    //        AcceStimulate ButtonAcce = ButtonObject.GetComponent<AcceStimulate>();
    //    }
    //}

    /// <summary>
    /// Perform normalise and matrix transformation here. 
    /// </summary>
    /// <param name="Pos"> Input position data here to start matrix transformatio. </param>
    /// <returns></returns>
    public Vector3 MatrixConversion(MixedRealityPose Pos)
    {
        Vector3 PosCoordinateCenter = triggeringPlane.transform.InverseTransformPoint(Pos.Position).normalized;
        return PosCoordinateCenter;
    }  
}
