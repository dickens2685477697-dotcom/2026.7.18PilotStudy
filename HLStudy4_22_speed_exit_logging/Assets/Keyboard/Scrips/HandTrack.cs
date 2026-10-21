using UnityEngine;
using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using Microsoft.MixedReality.Toolkit;
using UnityEngine.XR;
using System.Collections.Generic;
using UnityEngine.Events;

//struc = class without function
[System.Serializable]
public struct Gesture
{
    public string name;
    public List<Vector3> fingerDatas;
    public UnityEvent onRecognized;
}
public class HandTrack : MonoBehaviour
{
    public float threshold = 0.1f;
    public OVRSkeleton skeleton;
    public List<Gesture> gestures;
    public bool debugMode = true;
    private List<OVRBone> fingerBones;
    private Gesture previousGesture;

    void Start()
    {
        fingerBones = new List<OVRBone>(skeleton.Bones);
        previousGesture = new Gesture();
    }

    void Update()
    {
        if (debugMode && Input.GetKeyDown(KeyCode.LeftAlt))
        {
            Save();
        }

        //Gesture currentGesture = Recognize();
        //bool hasRecognized = !currentGesture.Equals(new Gesture());
        ////check if new gesture 
        //if(hasRecognized && currentGesture.Equals(previousGesture))
        //{
        //    //new gesture !!
        //    Debug.Log("New Gesture Found:" + currentGesture.name);
        //    previousGesture = currentGesture;
        //    currentGesture.onRecognized.Invoke();  
        //}
    }

    void Save()
    {
        Gesture g = new Gesture();
        g.name = "New Gesture";
        List<Vector3> data = new List<Vector3>();
        foreach (var bone in fingerBones)
        {
            //finger position relative to root
            data.Add(skeleton.transform.InverseTransformPoint(bone.Transform.position));
            //can compare the localPosition, localRotation, Flex of the finger or its distance;
        }
        g.fingerDatas = data;
        gestures.Add(g);
    }

    //Gesture Recognize()
    //{
    //    Gesture currentgesture = new Gesture();
    //    float currentMin = Mathf.Infinity;

    //    foreach(var gesture in gestures)
    //    {
    //        float sumDistance = 0;
    //        bool isDiscarded = false;
    //        for(int i = 0; i < fingerBones.Count; i++)
    //        {
    //            Vector3 currentData = skeleton.transform.InverseTransformPoint(fingerBones[i].Transform.position);
    //            float distance = Vector3.Distance(currentData, gesture.fingerDatas[i]);
    //            if (distance > threshold)
    //            {
    //                isDiscarded = true;
    //                break;
    //            }

    //            sumDistance += distance;
    //        }

    //        if(!isDiscarded && sumDistance < currentMin)
    //        {
    //            currentMin = sumDistance;
    //            currentgesture = gesture;
    //        }
    //    }

    //    return currentgesture;
    //}

}

