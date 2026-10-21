using System;
using System.Collections;
using System.Collections.Generic;
using System.ComponentModel;
using TMPro;
using UnityEngine;
using UnityEngine.Rendering;
using static KeyTriggeringBehavior;

[Serializable]
public class VisualFeedbacks
{
    public Material ActiveMaterial;
    public Material InactiveMaterial;
}

[Serializable]
public class HintPlaneBehaviors
{
    public GameObject HintPlane;
    public Renderer HintPlaneRenderer;
    public Material HintPlaneMaterial;

    public float FresnelPower;
    public Color HintPlaneColor;
    public float HintPlaneActivePower;
}

[Serializable]
public class KeyboardUtilities
{
    public AcceStimulateForKeyboard acce;
    public GetText gt;
    public CrossPlane cp;
}

[Serializable]
public class TextInputUtilities
{
    public GameObject Placeholder;
    public TextMeshProUGUI InputTextField;
    [SerializeField]
    public string InputText;
    public string ButtonText;
}

[Serializable]
public class ButtonAttributes
{
    public GameObject Button;
    public Renderer ButtonRenderer;
}

[Serializable]
public class ScriptConstants
{
    public Color PreEnteringColor = Color.grey;
    public Color EnteredColor = Color.black;
}

public class KeyTriggeringBehavior : MonoBehaviour
{
    public VisualFeedbacks VisualFeedback;
    public KeyboardUtilities Utilities;
    public TextInputUtilities TextInput;
    public ButtonAttributes Attributes;
    public ScriptConstants Variables;
    public HintPlaneBehaviors Hp;

    [Space()]
    public bool init = false;
    public bool keyTriggered = false;
    // Start is called before the first frame update
    void Start()
    {
        #region Initiation

        // Get Utilities
        Utilities.acce = GetComponent<AcceStimulateForKeyboard>();
        Utilities.gt = GetComponent<GetText>();
        Utilities.cp = GetComponent<CrossPlane>();

        // Get Button Attribute
        Attributes.Button = gameObject;
        Attributes.ButtonRenderer = GetComponent<Renderer>();

        // Get Text Utilities
        TextInput.InputText = TextInput.InputTextField.text;

        // Get Hint Plane
        Hp.HintPlaneRenderer = Hp.HintPlane.GetComponent<Renderer>();
        Hp.HintPlaneMaterial = Hp.HintPlaneRenderer.material;
        Hp.FresnelPower = Hp.HintPlaneMaterial.GetFloat("_FP");
        Hp.HintPlaneColor = Hp.HintPlaneMaterial.GetVector("_EmissionColor");
        Hp.HintPlaneActivePower = 0.2f;

        #endregion

        Hp.HintPlane.SetActive(false);

        Utilities.acce.InEvent.AddListener(()=>
        {
        });

        Utilities.cp.EnterEvent.AddListener(OnEntering);
        Utilities.acce.OutEvent.AddListener(OnOut);
        Utilities.acce.HesEvent.AddListener(() =>
        {
            Attributes.ButtonRenderer.material = VisualFeedback.InactiveMaterial;
            Utilities.gt.DestroyTempText();
        });
        Utilities.cp.ExitEvent.AddListener(OnExit);

        Utilities.cp.OutCancelZoneTrigger.AddListener(() =>
        {
            //print("OutCancelZone");
            Hp.HintPlaneMaterial.SetFloat("_FP", Hp.FresnelPower);
        });

        Utilities.cp.InCancelZoneTrigger.AddListener(() =>
        {
            //print("InCancalZone");
            Hp.HintPlaneMaterial.SetFloat("_FP", Hp.HintPlaneActivePower);
        });
    }

    /// <summary>
    /// On entering defines a series of actions triggering when the line crossing has happened.
    /// </summary>
    public void OnEntering()
    {
        // Change visual feedback
        Attributes.ButtonRenderer.material = VisualFeedback.ActiveMaterial;
        // Turn off placeholder if placeholder is active
        if (init == false)
        {
            TextInput.Placeholder.SetActive(false);
            init = true;
        }
        // Pre-Entering text
        Utilities.gt.InputStates("grey");
    }

    /// <summary>
    /// On Out defines a series of actions triggering when out event is triggering but Exit event is not
    /// </summary>
    public void OnOut()
    {
        // Set red plane active. 
        if (Utilities.cp.ExitEventTriggered == false)
        {
            Hp.HintPlane.SetActive(true);
        }
    }

    /// <summary>
    /// On Exit defines a series of actions triggering when Exit Event is triggering
    /// </summary>
    public void OnExit()
    {
        // Change Visual feedback
        Attributes.ButtonRenderer.material = VisualFeedback.InactiveMaterial;

        // Cancel condition 1: Check when exit, if the finger is within the red cancel zone.
        if (Utilities.cp.WithinCancelZone == false)
        {
            // Cancel condition 2: Check when exit, if Hes Event has been triggered.
            if (Utilities.cp.HesEventTriggered == false)
            {
                //print("1");
                /// Execute condition can only met when:
                /// 1. You are not in the red zone
                /// 2. You have not triggered the HesEvent cancel mechanism
                /// 3. You have both the enter event flag and in event flag set true 
                /// Explain: You have entered the key bound but not exiting the key bound from 
                /// other sides so you still have the InEvent set true. 
                if (Utilities.cp.EnterEventTriggered == true && Utilities.cp.InEventTriggered == true)
                {
                    //print("2");
                    Utilities.gt.CommitToInput();
                    keyTriggered = true;
                }
            }
        }
        // Destroy pre-entering text. 
        else
        {
            Utilities.gt.DestroyTempText();
        }

        Hp.HintPlane.SetActive(false);

        Utilities.cp.ExitEventTriggered = true;
        Utilities.cp.EnterEventTriggered = false;
    }
}
