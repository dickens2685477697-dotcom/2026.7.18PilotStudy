using Microsoft.MixedReality.Toolkit.Input;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class Keyboard010SetMode : MonoBehaviour
{
    public GameObject KeyObject;
    public Material ActionBarActiveMaterial, ActionBarCollideMaterial;
    public Material KeyActiveMaterial, KeyInactiveMaterial;
    public KeyOption KeyOpt;
    public GetText GT;
    public AcceStimulate Acce, ActionBarAcce;
    public TouchBlast TB, ActionBarTB;
    public GameObject ActionBar;
    public string SetMode;

    // Start is called before the first frame update
    void Start()
    {
        // Get component from action bar
        ActionBar = transform.Find("Cube").gameObject;
        ActionBarAcce = ActionBar.GetComponent<AcceStimulate>();
        ActionBarTB = ActionBar.GetComponent<TouchBlast>();

        // Deactivate action bar by default. 
        ActionBar.SetActive(false);

        // Get component from Key
        KeyOpt = gameObject.GetComponent<KeyOption>();
        Acce = gameObject.GetComponent<AcceStimulate>();
        TB = gameObject.GetComponent<TouchBlast>();
        GT = gameObject.GetComponent<GetText>();

        Acce.InMate = KeyActiveMaterial;
        Acce.OutMate = KeyInactiveMaterial;

        switch (SetMode)
        {
            case "Cancel":
                print("010CancelMode");

                Acce.HesEvent.AddListener(OpenActionBar);
                //Acce.OutEvent.AddListener(GT.InputStates);
                Acce.OutEvent.AddListener(CloseActionBar);

                ActionBarAcce.InEvent.AddListener(OpenCloseSti);
                ActionBarAcce.InEvent.AddListener(CloseActionBar);
                ActionBarAcce.InEvent.AddListener(UnInvokedAcce);
                break;

            case "Execute":
                print("010ExecuteMode");
                Acce.HesEvent.AddListener(OpenActionBar);
                // Acce.HesEvent.AddListener(KeyOpt.EnlargeSphereColliderRadius);
                Acce.OutEvent.AddListener(CloseActionBar);


                ActionBarAcce.InEvent.AddListener(OpenCloseSti);
                //ActionBarAcce.InEvent.AddListener(GT.InputStates);
                ActionBarAcce.InEvent.AddListener(CloseActionBar);
                ActionBarAcce.HesEvent.AddListener(UnInvokedAcce);

                break;
        }

    }

    public void OpenCloseSti()
    {
        Acce.OpenCloseSti();
    }
    public void OpenActionBar()
    {
        ActionBar.SetActive(true);
    }
    public void CloseActionBar()
    {
        ActionBarTB.SetInvoked(false);
        ActionBar.SetActive(false);
        ActionBarAcce.UnInvoked();
    }

    public void CloseActionBarAcce()
    {
        CloseActionBar();
    }

    public void UnInvokedAcce()
    {
        Acce.UnInvoked();
    }

    public void UnInvokedActionBarAcce()
    {
        ActionBarAcce.UnInvoked();
    }

    public void RestoreSphereColliderRadius(HandTrackingInputEventData eventData)
    {
        KeyOpt.RestoreSphereColliderRadius();
    }
}