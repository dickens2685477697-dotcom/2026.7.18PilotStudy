using Microsoft.MixedReality.Toolkit.UI;
using Oculus.Platform.Models;
using Oculus.Platform.Samples.VrHoops;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering.UI;

public class S1SetVariableForKeyboard : MonoBehaviour
{
    public Material OutMaterial;
    public Material InMaterial;
    // Mode 010 = no hesitation mode
    public bool Mode01, Mode010/*, Mode010Cancel, Mode010Exe*/, Long, Fast, FastForKeyboard, Acce, Velo, AcceOnly, AcceOld, showDebug;

    private void Start()
    {
        Init(gameObject);
        SetMaterial(gameObject);
        SetMode(gameObject);
    }
    public void Init(GameObject root)
    {
        if (root.transform.childCount == 0) return;
        foreach (Transform t in root.transform)
        {
            AcceStimulateForKeyboard acce;
            S1AccModeForKeyboard sam;
            acce = t.GetComponent<AcceStimulateForKeyboard>();
            sam = t.GetComponent<S1AccModeForKeyboard>();
            if (acce != null && sam != null)
            {
                sam.Acce = acce;
                // sam.Player = t.GetComponentInChildren<S1Player>();
            }
        }
    }
    public void SetMaterial(GameObject root)
    {
        AcceStimulateForKeyboard acce;
        acce = root.GetComponent<AcceStimulateForKeyboard>();
        
        if (acce != null)
        {
            acce.OutMate = OutMaterial;
            acce.InMate = InMaterial;
        }
        if (root.transform.childCount == 0) return;
        foreach (Transform t in root.transform)
        {
            SetMaterial(t.gameObject);
        }
    }

    public void SetMode(GameObject root)
    {
        AcceStimulateForKeyboard acce;
        acce = root.GetComponent<AcceStimulateForKeyboard>();
        if (acce != null)
        {
            SetAcce(acce);
        }
        if (root.transform.childCount == 0) return;
        foreach (Transform t in root.transform)
        {
            SetMode(t.gameObject); 
        }
    }

    public void SetAcce(AcceStimulateForKeyboard tas)
    {
        //Debug.LogFormat("{0}: setacce", tas.gameObject.name);
        tas.Delay = Long;
        tas.Fast = Fast;
        tas.FastForKeyboard = FastForKeyboard;
        tas.Acce = Acce;
        tas.Velo = Velo;
        tas.AcceOnly = AcceOnly;
        tas.AcceOld = AcceOld;
        tas.showDebug = showDebug;
        if (showDebug)
        {
            tas.Debugger = new TMPro.TMP_Text[4];
            foreach (Transform t in tas.transform)
            {
                if (t.gameObject.name == "A")
                    tas.Debugger[0] = t.GetComponent<TMPro.TMP_Text>();
                if (t.gameObject.name == "V")
                    tas.Debugger[1] = t.GetComponent<TMPro.TMP_Text>();
                if (t.gameObject.name == "T")
                    tas.Debugger[2] = t.GetComponent<TMPro.TMP_Text>();
                if (t.gameObject.name == "Con")
                    tas.Debugger[3] = t.GetComponent<TMPro.TMP_Text>();
            }
        }
        S1AccModeForKeyboard sam = tas.gameObject.GetComponent<S1AccModeForKeyboard>();
        if (Mode01)
        {
            print("01 Mode");
            sam.Set01Mode(); 
        }
        else if (Mode010)
        {
            print("010 Mode");
            sam.Set010Mode(); 
        }
        //else if (Mode010Cancel) 
        //{ sam.Set010cancelMode(); }
        else if (Fast)
        {
            print("Fast Mode");
            sam.SetFastMode(); 
        }
        else if (FastForKeyboard)
        {
            print("Keyboard Fast Mode");
            sam.SetKeyboardFastTapMode(); 
        }
        else if (Long || Velo || Acce || AcceOnly || AcceOld)
        {
            print("Hes Mode");
            sam.SetHesMode(); }
        else if (Acce)
        { tas.HesEvent.AddListener(tas.showDebugger); }
    }
}
