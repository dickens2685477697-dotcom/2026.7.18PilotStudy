using UnityEngine;
using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using UnityEngine.Events;

public class CrossPlane : MonoBehaviour
{

    public string triggeredButtonText;
    public bool init, crossed;

    public bool InEventTriggered = false, 
        HesEventTriggered = false, 
        OutEventTriggered = false,
        EnterEventTriggered = false,
        ExitEventTriggered = false,
        BoundTriggered = false;
    // Create UnityEvent to hear the Exit and entering of line
    public UnityEvent EnterEvent, ExitEvent, InCancelZoneTrigger, OutCancelZoneTrigger;

    // Get GameObject and Collider
    public GameObject KeyButton, Trigger;
    public Collider TriggerCollider;
    public Bounds TriggerBound;
    public Vector3 TriggerBoundCenter;

    // Get Script Class
    [Space(50)]
    public AcceStimulateForKeyboard  Acce;
    public GetText gt;

    // HandTracking Parameters
    [Header("Hand Tracking Parameters")]
    public Handedness handedness = Handedness.Any;
    public MixedRealityPose FingerTipPreviousPos;
    public MixedRealityPose FingerTipCurrentPos;
    public MixedRealityPose IndexDistalPose;
    public Vector3 FingerTipPreviousCoordinate;
    public Vector3 FingerTipCurrentCoordinate;
    public float FingerTipPreviousZ;
    public float FingerTipCurrentZ;

    public GameObject keyboardBoundingBox;
    public Bounds KeyboardBounds;
    public bool WithinCancelZone = true;

    public Vector3 FingertipPreviousConv;
    public Vector3 FingertipCurrentConv;

    // Start is called before the first frame update
    void Start()
    {
        KeyButton = gameObject;
        triggeredButtonText = KeyButton.name;
        Acce = GetComponent<AcceStimulateForKeyboard>();
        gt = gameObject.GetComponent<GetText>();

        Trigger = KeyButton.transform.Find("Trigger").gameObject;

        if(Trigger != null)
        {
            TriggerCollider = Trigger.GetComponent<Collider>();
            TriggerBound = TriggerCollider.bounds;
            TriggerBoundCenter = TriggerBound.center;

        }

        Acce.InEvent.AddListener(() =>
        {
            //print(triggeredButtonText);
            InEventTriggered = true;
        });

        Acce.HesEvent.AddListener(() =>
        {
            HesEventTriggered = true;
        });

        Acce.OutEvent.AddListener(() =>
        {
            OutEventTriggered = true;
            HesEventTriggered = false;
        });

        EnterEvent.AddListener(() =>
        {
            ExitEventTriggered = false;
            EnterEventTriggered = true;
        });

        ExitEvent.AddListener(() =>
        {
            //if (EnterEventTriggered == true && InEventTriggered == true)
            //{
            //    gt.InputStates("black");
            //}
            InEventTriggered = false;
            ExitEventTriggered = true;
            EnterEventTriggered = false;
        });
    }

    // Update is called once per frame
    void FixedUpdate()
    {
        KeyboardBounds = keyboardBoundingBox.GetComponent<Collider>().bounds;

        if (TriggerCollider != null)
        {
            TriggerBound = TriggerCollider.bounds;
        }
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, Handedness.Any, out FingerTipCurrentPos))
        {
            HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexDistalJoint, Handedness.Any, out IndexDistalPose);
            if (init)
            {
                init = false;
                FingerTipPreviousPos = FingerTipCurrentPos;
                return;
            }

            FingertipPreviousConv = MatrixConversion(FingerTipPreviousPos);
            FingertipCurrentConv = MatrixConversion(FingerTipCurrentPos);
            FingerTipPreviousZ = FingertipPreviousConv.z;
            FingerTipCurrentZ = FingertipCurrentConv.z;

            CheckInsideKeyboardBounds(FingerTipPreviousPos.Position, FingerTipCurrentPos.Position);

            if (FingerTipCurrentZ != FingerTipPreviousZ)
            {
                EnterCrossPlaneChecker(FingerTipCurrentZ, FingerTipPreviousZ);
                ExitCrossPlaneChecker(FingerTipCurrentZ, FingerTipPreviousZ);
                if (crossed == true)
                {
                    // print("Crossed");
                    // setColliderActive(true);

                    if (InEventTriggered)
                    {
                        //print("In Event set false");
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
            HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, Handedness.Any, out FingerTipCurrentPos);
            HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexDistalJoint, Handedness.Any, out IndexDistalPose);
        }

    }

    /// <summary>
    /// Perform normalise and matrix transformation here. 
    /// </summary>
    /// <param name="Pos"> Input position data here to start matrix transformatio. </param>
    /// <returns></returns>

    public void CheckInsideKeyboardBounds(Vector3 CurrentFramePos, Vector3 PreviousFramePos)
    {
        if (KeyboardBounds.Contains(CurrentFramePos) || KeyboardBounds.Contains(PreviousFramePos))
        {
            //print("In");
            OutCancelZoneTrigger.Invoke();
            WithinCancelZone = false;
        }
        else
        {
            InCancelZoneTrigger.Invoke();
            WithinCancelZone = true;
        }
    }

    public Vector3 MatrixConversion(MixedRealityPose Pos)
    {
        Vector3 PosCoordinateCenter = Trigger.transform.InverseTransformPoint(Pos.Position).normalized;
        return PosCoordinateCenter;
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
        TriggerBound = TriggerCollider.bounds;

        if (TriggerBound.Contains(FingerTipCurrentPos.Position) || TriggerBound.Contains(IndexDistalPose.Position))
        {
            BoundTriggered = true;
            if (CurrentFramePos > 0 && CurrentFramePos > PreviousFramePos && PreviousFramePos < 0)
            {
                //print("Enter");
                EnterEvent.Invoke();
            }
        }
    }

    public void ExitCrossPlaneChecker(float CurrentFramePos, float PreviousFramePos)
    {
        TriggerBound = TriggerCollider.bounds;

        if (CurrentFramePos < 0 && CurrentFramePos < PreviousFramePos && PreviousFramePos > 0)
        {
            //print("Exit");
            ExitEvent.Invoke(); 
        }

    }
}
