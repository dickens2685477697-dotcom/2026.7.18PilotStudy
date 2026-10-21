
using UnityEngine;

public class Constraint : MonoBehaviour
{
    // Debug switch
    public bool DebugSwitch = true;

    // Bool access from other script as a switch to control triggering the key button. 
    static public bool EnteredFromAbove;

    // Bools to check if finger is within the area
    //bool withinXRange = false;
    //bool withinZRange = false;
    // Set minimum triggering distance
    // public float triggerDistance = 1.0f;
    //public float ForwardThreshold = 0.9f;
    //public float dot;
    // public Vector3 Velocity;
    //public Vector3 RelativeFingerTipPose;
    //public Vector3 KeyboardSize;

    /// <summary>
    /// This indicate how much the vector is needed to align with the area in order to successfully triggering the button
    /// Dot product will return a value between 1 and -1, where -1 is completely misaligned, therefore 0.9 is a pretty strict alignment threshold
    /// Consider lower the threshold depending on the size, shape and distance of the object. 
    /// </summary>
    public float triggeringThreshold = 0.9f;

    // Setting up delegate
    public delegate bool MyDelegate();
    public MyDelegate EnteredFromAboveDelegate;

    // The trigger plane in front of the object.
    public Vector3 triggerPlaneCenter;
    //public Vector3 triggerPlaneExtents;
    public Vector3 FingerPose1;
    public Vector3 FingerPose2;

    // Get finger position from AcceStimulate to save the memory storing another sets of data. 
    public AcceStimulate acce;
    // Get the Keyboard button collider from here Possibly not useful though. 
    public GameObject keyboardButton;
    public Transform keyboardButtonTransform;
    public Vector3 KeyboardButtonCenter;
    public Renderer KeyboardButtonRenderer;

    // public float triggerDistance=0.1f;
    // public Vector3 FingerDistalPose;

    public Collider triggerCollider;
    public GameObject triggerPlane;
    public Renderer triggerPlaneRenderer;
    Bounds triggerBounds;


    // Vector3 of the finger tip position. 

    public void Start()
    {
        // EnteredFromAboveDelegate = new MyDelegate(triggeringChecker);

        acce = gameObject.GetComponent<AcceStimulate>();

        // Get gameobjet at start
        keyboardButton = gameObject;
        keyboardButtonTransform = keyboardButton.GetComponent<Transform>();

        triggerPlane = GameObject.FindGameObjectWithTag("Trigger");
        triggerCollider = triggerPlane.GetComponent<Collider>();
        triggerBounds = triggerCollider.bounds;
        KeyboardButtonRenderer = keyboardButton.GetComponent<Renderer>();
        KeyboardButtonCenter = KeyboardButtonRenderer.bounds.center;

        triggerPlaneRenderer = triggerPlane.GetComponent<Renderer>();
        // MeshFilter meshFilter = triggerPlane.GetComponent<MeshFilter>();
        triggerPlaneCenter = triggerPlaneRenderer.bounds.center;
        // if (meshFilter != null && meshFilter.mesh != null)
        // {
        //     triggerPlaneExtents = triggerPlaneRenderer.bounds.extents;
        // }
        // KeyboardSize = keyboardButton.GetComponent<Renderer>().bounds.size;

        // Get the triggeringplane game object through tag


        // if (triggerPlane == null && DebugSwitch == true)
        // {
        //     Debug.LogError("TriggerObject Not Found");
        // }

    } 

    private void FixedUpdate()
    {
        acce.IndexTipPose1.Position = FingerPose1;
        acce.IndexTipPose2.Position = FingerPose2;

        #region VectorDirection Method

        //FingerTipPose = acce.IndexTipPose1.Position;
        //Vector3 Direction = (KeyboardButtonCenter - FingerTipPose).normalized;
        //print(Direction);
        //if (Vector3.Dot(Direction, keyboardButton.transform.up)> triggeringThreshold)
        //{
        //    print("111");
        //    EnteredFromAbove = true;
        //}
        //else
        //{
        //    EnteredFromAbove = false;
        //}

        #endregion
        #region line Crossing
        //TestWithinX();
        //TestWithinZ();
        //FingerTipPose = acce.IndexTipPose1.Position;
        //RelativeFingerTipPose = triggerPlane.transform.InverseTransformPoint(FingerTipPose);

        //if (RelativeFingerTipPose.y*1000 <= triggerPlaneCenter.y*1000 && withinXRange && withinZRange)
        //{
        //    print("in");
        //}
        #endregion
        #region Archive-NotWorking-RayCast Method
        ///// InverseTransformPoint converts FingerTipPose from world position to local position, we need to detect if we are at top of the object's local position
        ///// +Vector3.up ensures the ray was cast from the top
        ///// Vector.down sets the direction making sure it point down to the local space of the object. 
        ///// The whole line creates a Ray object with the starting point set to fingertipPose and direction set to pointing downwards. 

        //Ray ray1 = new Ray(transform.InverseTransformPoint(FingerTipPose), Vector3.down);
        //Ray ray2 = new Ray(transform.InverseTransformPoint(FingerTipPose) + Vector3.up, Vector3.down);
        //RaycastHit hit;
        //print(ray1);

        //// print(transform.InverseTransformPoint(FingerTipPose)+Vector3.up);

        //if (Physics.Raycast(ray1, out hit, triggerDistance))
        //{
        //    if (hit.collider.gameObject == triggerPlane &&
        //        Vector3.Dot(hit.normal, transform.up) > 0.9f && Vector3.Dot(hit.normal, -ray1.direction) > 0.9f)
        //    {
        //        EnteredFromAbove = true;
        //    }
        //    else
        //    {
        //        EnteredFromAbove = false;
        //    }
        //}
        //else EnteredFromAbove = false;

        //if(DebugSwitch == true) 
        //{
        //    Debug.DrawRay(transform.TransformPoint(ray1.origin), transform.TransformDirection(ray1.direction) * triggerDistance, Color.yellow);
        //}
        #endregion

    }

    public  void triggeringChecker()
    {
        #region Raycast Checker Switcher method.
        Ray ray = new Ray(acce.IndexTipPose1.Position, triggerPlaneCenter);
        RaycastHit hitInfo;
        if (triggerCollider.Raycast(ray, out hitInfo, 0.1f))
        {
            //print("InEvent");
            EnteredFromAbove = true;
            //print(Constraint.EnteredFromAbove);
        }
        else EnteredFromAbove = false;
        //print(Constraint.EnteredFromAbove + "InEvent");
        #endregion
    }

    #region redundancies
    //public bool TestWithinX()
    //{
    //    if (RelativeFingerTipPose.x >= -triggerPlaneExtents.x &&
    //        RelativeFingerTipPose.x <= triggerPlaneExtents.x)
    //    {
    //        withinXRange = true;
    //        print("within X");
    //    }
    //    else
    //    {
    //        withinXRange = false;
    //    }
    //    return withinXRange;
    //}

    //public bool TestWithinZ()
    //{
    //    if (RelativeFingerTipPose.z >= -triggerPlaneExtents.z &&
    //        RelativeFingerTipPose.z <= triggerPlaneExtents.z)
    //    {
    //        withinZRange = true;
    //        print("within Y");
    //    }
    //    else
    //    {
    //        withinZRange = false;
    //    }
    //    return withinZRange;
    //}
    #endregion
}