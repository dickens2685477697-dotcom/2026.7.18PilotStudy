using UnityEngine;
using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using UnityEngine.Rendering;
using UnityEngine.ProBuilder.MeshOperations;
using Oculus.Voice.Demo;
using UnityEngine.Events;
using System.Collections.Generic;
using System.Runtime.CompilerServices;

public class KeyBeh : MonoBehaviour
{
    // Get GameObject - Key and Trigger
    public GameObject key, trigger, textCanvas;

    public Material keyInactiveMaterial, keyActiveMaterial, triggerInactiveMaterial, triggerActiveMaterial;

    public Collider parentCollider, triggerCollider;

    public UnityEvent EnteredEvent, ExitedEvent;

    public float distanceOnEnterMove = 0.1f;

    private bool movedOnEnter = false;

    private string getTextString()
    {
        string keyValue = GetComponent<Renderer>().name;
        return keyValue; 
    }
    private void Start()
    {
        getTextString();
        print(getTextString());
    }
    private void Awake()
    {
        parentCollider = GetComponent<Collider>();
        if (trigger != null)
        {
            trigger.SetActive(false);
        }
    }

    private void Update()
    {
        CheckFingerJoint(Handedness.Left);
        CheckFingerJoint(Handedness.Right);
    }

    private void CheckFingerJoint(Handedness handedness)
    {
        Vector3 indexTipPosition;
        Vector3 indexDistalPosition;

        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, handedness, out MixedRealityPose indexTipPose))
        {
            indexTipPosition = indexTipPose.Position;
        }
        else
        {
            return;
        }

        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexDistalJoint, handedness, out MixedRealityPose indexDistalPose))
        {
            indexDistalPosition = indexDistalPose.Position;
        }
        else
        {
            return;
        }

        if (parentCollider.bounds.Contains(indexTipPosition) || parentCollider.bounds.Contains(indexDistalPosition))
        {
            EnteredEvent.Invoke();
            key.GetComponent<Renderer>().material = keyActiveMaterial;
            trigger.SetActive(true);
        }
        else
        {
            ExitedEvent.Invoke();
            key.GetComponent<Renderer>().material = keyInactiveMaterial;
            trigger.SetActive(false);
        }

        if (triggerCollider.bounds.Contains(indexTipPosition) || triggerCollider.bounds.Contains(indexDistalPosition))
        {
            trigger.GetComponent<Renderer>().material = triggerInactiveMaterial;
        }
        else
        {
            trigger.GetComponent<Renderer>().material = triggerActiveMaterial;
        }
    }
}
