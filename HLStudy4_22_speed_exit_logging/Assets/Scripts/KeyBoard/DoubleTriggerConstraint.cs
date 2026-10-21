using System.Collections;
using System.Collections.Generic;
using System.Runtime.ExceptionServices;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.Rendering;

public class DoubleTriggerConstraint : MonoBehaviour
{
    public List<GameObject> Buttons = new List<GameObject>();
    public bool CanTrigger = true;

    // Start is called before the first frame update
    private void Start()
    {
       
    }
    void FixedUpdate()
    {
        foreach (Transform child in transform)
        {
            AcceStimulate acce = child.GetComponent<AcceStimulate>();
            if (acce != null)
            {
            }
        }
    }

    public bool triggeringSwitch()
    {
        if (CanTrigger == true)
        {
            CanTrigger = false;
        }
        else if (CanTrigger == false)
        {
            CanTrigger = true;
        }

        return CanTrigger;
    }
}
