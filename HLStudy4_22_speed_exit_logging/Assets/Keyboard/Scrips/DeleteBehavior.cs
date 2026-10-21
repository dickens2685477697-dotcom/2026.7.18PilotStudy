using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

public class DeleteBehavior : MonoBehaviour
{

    public GetText gettext;
    public TextMeshPro textUpdate;
    public AcceStimulate acce;

    public float DeleteInterval = 10f;
    public float PressTime = 1f;
    public float ThresholdSlowDelete = 3f,
        ThresholdFastDelete = 8f,
        InTime = 0f;

    // Start is called before the first frame update
    void Start()
    {
        acce = gameObject.GetComponent<AcceStimulate>();
    }

    // Update is called once per frame

    public void TriggerDelete()
    {
        if(acce.Invoked == true)
        {
            DeleteShortPress();
            InTime += 1f;
            if (InTime >= ThresholdSlowDelete)
            {
                DeleteInterval = 5f;
                DeleteLongPress(5f);
            }
        }
    }
    /// <param name="Delete">Delete Key Function</param>
    public void DeleteShortPress()
    {
        if (textUpdate.text.Length > 0)
        {
            textUpdate.text = textUpdate.text.Substring(0, textUpdate.text.Length - 1);
        }
    }

    public void DeleteLongPress(float Interval)
    {
        InvokeRepeating("DeleteShortPress" ,PressTime, 1f / Interval);
    }
}
